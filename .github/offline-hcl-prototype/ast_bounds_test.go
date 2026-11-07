package hclprototype

import (
	"reflect"
	"strings"
	"testing"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/hclsyntax"
)

type processingEvidence struct {
	nodes     int
	depth     int
	maxDepth  int
	binaryOps int
}

func (e *processingEvidence) Enter(node hclsyntax.Node) hcl.Diagnostics {
	e.nodes++
	e.depth++
	if e.depth > e.maxDepth {
		e.maxDepth = e.depth
	}
	if _, ok := node.(*hclsyntax.BinaryOpExpr); ok {
		e.binaryOps++
	}
	return nil
}

func (e *processingEvidence) Exit(_ hclsyntax.Node) hcl.Diagnostics {
	e.depth--
	return nil
}

func chainSource(terms int) []byte {
	return []byte("locals { value = " + strings.Repeat("1+", terms-1) + "1 }")
}

func measureProcessing(t *testing.T, source []byte) (processingEvidence, int, int) {
	t.Helper()
	tokens, diagnostics := hclsyntax.LexConfig(source, "synthetic.tf", hcl.InitialPos)
	if len(diagnostics) != 0 {
		t.Fatal("synthetic chain did not lex without diagnostics")
	}
	depth, lexicalDepth := 0, 0
	for _, token := range tokens {
		switch token.Type {
		case hclsyntax.TokenOBrace, hclsyntax.TokenOBrack, hclsyntax.TokenOParen,
			hclsyntax.TokenOQuote, hclsyntax.TokenTemplateInterp, hclsyntax.TokenTemplateControl:
			depth++
		case hclsyntax.TokenCBrace, hclsyntax.TokenCBrack, hclsyntax.TokenCParen,
			hclsyntax.TokenCQuote, hclsyntax.TokenTemplateSeqEnd:
			depth--
		}
		if depth > lexicalDepth {
			lexicalDepth = depth
		}
	}
	file, diagnostics := hclsyntax.ParseConfig(source, "synthetic.tf", hcl.InitialPos)
	if len(diagnostics) != 0 || file == nil {
		t.Fatal("synthetic chain did not parse without diagnostics")
	}
	body, ok := file.Body.(*hclsyntax.Body)
	if !ok {
		t.Fatal("synthetic chain has an unexpected body")
	}
	var evidence processingEvidence
	hclsyntax.Walk(body, &evidence)
	if evidence.depth != 0 {
		t.Fatal("unbalanced observer walk")
	}
	return evidence, len(tokens), lexicalDepth
}

func TestActualOperatorChainsAtASTDepthThreshold(t *testing.T) {
	reference, _, _ := measureProcessing(t, chainSource(2))
	overhead := reference.maxDepth - 2
	tests := []struct {
		name       string
		depth      int
		categories []string
	}{
		{"just below", MaxASTDepth - 1, []string{"unsupported_expression"}},
		{"exactly at", MaxASTDepth, []string{"unsupported_expression"}},
		{"just above", MaxASTDepth + 1, []string{"bounds_refused", "unsupported_expression"}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			terms := test.depth - overhead
			source := chainSource(terms)
			evidence, tokens, lexicalDepth := measureProcessing(t, source)
			if evidence.maxDepth != test.depth || evidence.binaryOps != terms-1 {
				t.Fatalf("parser shape changed: measured depth=%d ops=%d", evidence.maxDepth, evidence.binaryOps)
			}
			if len(source) > MaxBytes || tokens > MaxTokens || lexicalDepth > MaxLexDepth {
				t.Fatal("case hit an independent pre-parse bound")
			}
			result := Analyze(NativeHCL, source)
			if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories, test.categories) {
				t.Fatalf("wrong exact refusal categories: %+v", result)
			}
			if result.Nodes != evidence.nodes || evidence.nodes > MaxNodes {
				t.Fatal("reported count does not match complete processing of this case")
			}
			t.Logf("terms=%d bytes=%d tokens=%d lexical_depth=%d ast_depth=%d visited_nodes=%d",
				terms, len(source), tokens, lexicalDepth, evidence.maxDepth, evidence.nodes)
		})
	}
}

func TestLongOperatorChainWithinIndependentBounds(t *testing.T) {
	_, oneTermTokens, _ := measureProcessing(t, chainSource(1))
	wrapperTokens := oneTermTokens - 1
	terms := (MaxTokens - wrapperTokens + 1) / 2
	source := chainSource(terms)
	_, tokens, _ := measureProcessing(t, source)
	for tokens < MaxTokens {
		source = append(source, '\n')
		_, tokens, _ = measureProcessing(t, source)
	}
	evidence, tokens, lexicalDepth := measureProcessing(t, source)
	if len(source) > MaxBytes || tokens != MaxTokens || lexicalDepth > MaxLexDepth {
		t.Fatal("long chain did not remain at the independent token limit")
	}
	if evidence.maxDepth <= MaxASTDepth || evidence.nodes > MaxNodes || evidence.binaryOps != terms-1 {
		t.Fatal("long chain did not exercise full deep-tree processing below the node-count threshold")
	}
	result := Analyze(NativeHCL, source)
	if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories,
		[]string{"bounds_refused", "unsupported_expression"}) {
		t.Fatalf("wrong exact long-chain categories: %+v", result)
	}
	if result.Nodes != evidence.nodes {
		t.Fatal("walker processing was not the complete parser-built tree")
	}
	t.Logf("largest_tested_chain terms=%d bytes=%d tokens=%d lexical_depth=%d ast_depth=%d visited_nodes=%d",
		terms, len(source), tokens, lexicalDepth, evidence.maxDepth, evidence.nodes)

	overTokenBound := append(append([]byte{}, source...), '\n')
	over := Analyze(NativeHCL, overTokenBound)
	if over.Outcome != "refused" || !reflect.DeepEqual(over.Categories, []string{"bounds_refused"}) ||
		over.Nodes != 0 || over.Objects != 0 || over.ObjectKeys != 0 {
		t.Fatalf("over-token case did not stop before AST analysis: %+v", over)
	}
}

func TestLongOperatorLookingTextRemainsInert(t *testing.T) {
	text := strings.Repeat("1+", 4092) + "1"
	sources := []string{
		`locals { value = "` + text + `" }`,
		"# " + text + "\nlocals { value = 1 }\n",
		"/* " + text + " */\nlocals { value = 1 }\n",
		"locals {\n value = <<EOF\n" + text + "\nEOF\n}\n",
	}
	for index, source := range sources {
		if len(source) > MaxBytes {
			t.Fatal("inert text case exceeds byte bound")
		}
		evidence, _, _ := measureProcessing(t, []byte(source))
		if evidence.binaryOps != 0 {
			t.Fatal("inert text unexpectedly produced operator nodes")
		}
		result := Analyze(NativeHCL, []byte(source))
		if result.Outcome != "accepted_predicate" || len(result.Categories) != 0 {
			t.Fatalf("inert operator-looking text case %d refused: %+v", index, result)
		}
	}
}
