package hclprototype

import (
	"reflect"
	"strconv"
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
	if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories, []string{"bounds_refused"}) {
		t.Fatalf("wrong exact long-chain categories: %+v", result)
	}
	if result.Nodes != 0 || result.Objects != 0 || result.ObjectKeys != 0 {
		t.Fatal("operator budget did not stop the analyzer before AST analysis")
	}
	t.Logf("independent_parser_walk terms=%d bytes=%d tokens=%d lexical_depth=%d ast_depth=%d visited_nodes=%d analyzer_nodes=%d",
		terms, len(source), tokens, lexicalDepth, evidence.maxDepth, evidence.nodes, result.Nodes)

	overTokenBound := append(append([]byte{}, source...), '\n')
	over := Analyze(NativeHCL, overTokenBound)
	if over.Outcome != "refused" || !reflect.DeepEqual(over.Categories, []string{"bounds_refused"}) ||
		over.Nodes != 0 || over.Objects != 0 || over.ObjectKeys != 0 {
		t.Fatalf("over-token case did not stop before AST analysis: %+v", over)
	}
}

func TestOperatorBudgetExactBoundary(t *testing.T) {
	tests := []struct {
		name         string
		operators    int
		categories   []string
		earlyRefusal bool
	}{
		{"at budget", MaxOperatorTokens, []string{"bounds_refused", "unsupported_expression"}, false},
		{"above budget", MaxOperatorTokens + 1, []string{"bounds_refused"}, true},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			source := chainSource(test.operators + 1)
			evidence, tokens, lexicalDepth := measureProcessing(t, source)
			if len(source) > MaxBytes || tokens > MaxTokens || lexicalDepth > MaxLexDepth ||
				evidence.binaryOps != test.operators {
				t.Fatal("budget case did not exercise the intended parser shape")
			}
			result := Analyze(NativeHCL, source)
			if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories, test.categories) {
				t.Fatalf("wrong exact budget refusal: %+v", result)
			}
			if test.earlyRefusal && (result.Nodes != 0 || result.Objects != 0 || result.ObjectKeys != 0) {
				t.Fatal("above-budget input reached AST analysis")
			}
			if !test.earlyRefusal && result.Nodes != evidence.nodes {
				t.Fatal("at-budget input did not complete AST analysis")
			}
			t.Logf("operator_budget operators=%d bytes=%d tokens=%d ast_depth=%d independent_nodes=%d analyzer_nodes=%d",
				test.operators, len(source), tokens, evidence.maxDepth, evidence.nodes, result.Nodes)
		})
	}
}

func TestOperatorBudgetTokenKinds(t *testing.T) {
	tests := []struct {
		spelling string
		kind     hclsyntax.TokenType
	}{
		{"+", hclsyntax.TokenPlus}, {"-", hclsyntax.TokenMinus},
		{"*", hclsyntax.TokenStar}, {"/", hclsyntax.TokenSlash},
		{"%", hclsyntax.TokenPercent}, {"==", hclsyntax.TokenEqualOp},
		{"!=", hclsyntax.TokenNotEqual}, {"<", hclsyntax.TokenLessThan},
		{"<=", hclsyntax.TokenLessThanEq}, {">", hclsyntax.TokenGreaterThan},
		{">=", hclsyntax.TokenGreaterThanEq}, {"&&", hclsyntax.TokenAnd},
		{"||", hclsyntax.TokenOr}, {"!", hclsyntax.TokenBang},
		{"?", hclsyntax.TokenQuestion},
	}
	for _, test := range tests {
		t.Run(test.spelling, func(t *testing.T) {
			source := []byte("locals { value = 1 " +
				strings.Repeat(test.spelling+" 1 ", MaxOperatorTokens+1) + "}")
			tokens, diagnostics := hclsyntax.LexConfig(source, "synthetic.tf", hcl.InitialPos)
			if len(diagnostics) != 0 || len(source) > MaxBytes || len(tokens) > MaxTokens {
				t.Fatal("operator example did not lex within independent bounds")
			}
			count := 0
			for _, token := range tokens {
				if token.Type == test.kind {
					count++
				}
			}
			if count != MaxOperatorTokens+1 {
				t.Fatal("operator example did not produce the expected lexer token kind")
			}
			result := Analyze(NativeHCL, source)
			if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories, []string{"bounds_refused"}) ||
				result.Nodes != 0 {
				t.Fatalf("operator kind did not trigger pre-parse budget: %+v", result)
			}
		})
	}
}

func TestLongOperatorLookingTextRemainsInert(t *testing.T) {
	texts := []string{
		strings.Repeat("1+", 4092) + "1",
		strings.Repeat("+ - * / % == != < <= > >= && || ! ? ", 300),
	}
	for _, text := range texts {
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
	var source strings.Builder
	source.WriteString("locals {\n")
	for index := 0; index < MaxOperatorTokens+1; index++ {
		source.WriteString(" value-")
		source.WriteString(strconv.Itoa(index))
		source.WriteString(" = var.items.name\n")
	}
	source.WriteString("}\n")
	result := Analyze(NativeHCL, []byte(source.String()))
	if result.Outcome != "accepted_predicate" || len(result.Categories) != 0 {
		t.Fatalf("ordinary assignments or hyphenated identifiers refused: %+v", result)
	}
}

func TestWalkerDoesNotPruneAtNodeCountThreshold(t *testing.T) {
	// Fabricated AST: this is not a claim that an admitted source can produce
	// this many nodes under the independent token limit.
	body := &hclsyntax.Body{}
	for index := 0; index < MaxNodes/4+16; index++ {
		body.Blocks = append(body.Blocks, &hclsyntax.Block{
			Type: "ordinary", Body: &hclsyntax.Body{},
		})
	}
	body.Blocks = append(body.Blocks, &hclsyntax.Block{
		Type: "provider", Body: &hclsyntax.Body{},
	})
	var evidence processingEvidence
	hclsyntax.Walk(body, &evidence)
	if evidence.nodes <= MaxNodes {
		t.Fatal("fabricated AST did not exceed the refusal threshold")
	}
	state := &analysis{categories: make(map[string]bool)}
	hclsyntax.Walk(body, state)
	result := state.finish()
	if result.Nodes != MaxNodes || result.Outcome != "refused" ||
		!reflect.DeepEqual(result.Categories, []string{"bounds_refused", "provider_block"}) {
		t.Fatalf("node threshold pruned or failed to cap reporting: %+v", result)
	}
	t.Logf("fabricated_ast_visited_nodes=%d reported_nodes=%d final_provider_visited=true",
		evidence.nodes, result.Nodes)
}
