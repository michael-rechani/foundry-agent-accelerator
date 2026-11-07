// Package hclprototype implements a synthetic-input-only syntax predicate.
// It is not connected to the conservative scanner or a runtime authorization gate.
package hclprototype

import (
	"sort"
	"unicode/utf8"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/hclsyntax"
	"github.com/zclconf/go-cty/cty"
)

const (
	NativeHCL   = "native-hcl"
	MaxBytes    = 65536
	MaxTokens   = 8192
	MaxOperatorTokens = 256
	MaxLexDepth = 32
	MaxNodes    = 16384
	MaxASTDepth = 128
)

// Result contains only fixed categories and bounded counts, never source or diagnostics.
type Result struct {
	Outcome    string
	Categories []string
	Nodes      int
	Objects    int
	ObjectKeys int
}

type analysis struct {
	result     Result
	categories map[string]bool
	depth      int
	blocks     []string
	truncated  bool
}

func (a *analysis) refuse(category string) {
	a.categories[category] = true
}

func (a *analysis) finish() Result {
	if a.truncated {
		// Prefix counts and categories can depend on HCL body map order.
		return Result{Outcome: "refused", Categories: []string{"bounds_refused"}}
	}
	a.result.Outcome = "accepted_predicate"
	if len(a.categories) != 0 {
		a.result.Outcome = "refused"
	}
	a.result.Categories = make([]string, 0, len(a.categories))
	for category := range a.categories {
		a.result.Categories = append(a.result.Categories, category)
	}
	sort.Strings(a.result.Categories)
	return a.result
}

// Analyze accepts only native HCL bytes. No filesystem, evaluation context,
// function execution, module resolution, JSON parser, or provider execution is used.
func Analyze(format string, source []byte) Result {
	a := &analysis{categories: make(map[string]bool)}
	if format != NativeHCL {
		a.refuse("format_refused")
		return a.finish()
	}
	if len(source) == 0 || len(source) > MaxBytes {
		a.refuse("bounds_refused")
		return a.finish()
	}
	if !utf8.Valid(source) {
		a.refuse("encoding_refused")
		return a.finish()
	}
	tokens, diagnostics := hclsyntax.LexConfig(source, "synthetic.tf", hcl.InitialPos)
	if len(diagnostics) != 0 {
		a.refuse("syntax_refused")
		return a.finish()
	}
	if len(tokens) > MaxTokens {
		a.refuse("bounds_refused")
		return a.finish()
	}
	depth := 0
	operatorTokens := 0
	for _, token := range tokens {
		if operatorToken(token.Type) {
			operatorTokens++
			if operatorTokens > MaxOperatorTokens {
				a.refuse("bounds_refused")
				return a.finish()
			}
		}
		switch token.Type {
		case hclsyntax.TokenOBrace, hclsyntax.TokenOBrack, hclsyntax.TokenOParen,
			hclsyntax.TokenOQuote, hclsyntax.TokenTemplateInterp, hclsyntax.TokenTemplateControl:
			depth++
		case hclsyntax.TokenCBrace, hclsyntax.TokenCBrack, hclsyntax.TokenCParen,
			hclsyntax.TokenCQuote, hclsyntax.TokenTemplateSeqEnd:
			depth--
		}
		if depth > MaxLexDepth {
			a.refuse("bounds_refused")
			return a.finish()
		}
		if depth < 0 {
			a.refuse("syntax_refused")
			return a.finish()
		}
	}
	file, diagnostics := hclsyntax.ParseConfig(source, "synthetic.tf", hcl.InitialPos)
	if len(diagnostics) != 0 || file == nil {
		a.refuse("syntax_refused")
		return a.finish()
	}
	body, ok := file.Body.(*hclsyntax.Body)
	if !ok {
		a.refuse("unsupported_structure")
		return a.finish()
	}
	a.walk(body)
	return a.finish()
}

// This is an input budget for known structural operator tokens, not a general
// AST-depth, parser-stack, or execution-time bound. Lexer-produced literal
// string, heredoc and comment tokens are not counted as operators.
func operatorToken(kind hclsyntax.TokenType) bool {
	switch kind {
	case hclsyntax.TokenPlus, hclsyntax.TokenMinus, hclsyntax.TokenStar,
		hclsyntax.TokenSlash, hclsyntax.TokenPercent, hclsyntax.TokenEqualOp,
		hclsyntax.TokenNotEqual, hclsyntax.TokenLessThan, hclsyntax.TokenLessThanEq,
		hclsyntax.TokenGreaterThan, hclsyntax.TokenGreaterThanEq,
		hclsyntax.TokenAnd, hclsyntax.TokenOr, hclsyntax.TokenBang, hclsyntax.TokenQuestion:
		return true
	default:
		return false
	}
}


func routingName(name string) bool {
	switch name {
	case "provider", "providers", "alias", "configuration_aliases":
		return true
	default:
		return false
	}
}

// The bare-key special case mirrors HCL's ObjectConsKeyExpr semantics.
// ForceNonLiteral is checked before stripping parentheses, so (provider)
// remains a variable reference, never a literal spelling of the key.
func keyName(expr hclsyntax.Expression) (string, bool) {
	key, ok := expr.(*hclsyntax.ObjectConsKeyExpr)
	if !ok {
		return "", false
	}
	if !key.ForceNonLiteral {
		if name := hcl.ExprAsKeyword(key.Wrapped); name != "" {
			return cty.StringVal(name).AsString(), true
		}
	}
	return literalString(key.Wrapped)
}

func literalString(expr hclsyntax.Expression) (string, bool) {
	switch value := expr.(type) {
	case *hclsyntax.ParenthesesExpr:
		return literalString(value.Expression)
	case *hclsyntax.TemplateExpr:
		if !value.IsStringLiteral() {
			return "", false
		}
		return literalString(value.Parts[0])
	case *hclsyntax.LiteralValueExpr:
		if value.Val.IsKnown() && !value.Val.IsNull() && value.Val.Type().Equals(cty.String) {
			return value.Val.AsString(), true
		}
	}
	return "", false
}

func (a *analysis) checkObject(object *hclsyntax.ObjectConsExpr) {
	if a.result.Objects < MaxNodes {
		a.result.Objects++
	}
	seen := make(map[string]bool)
	for _, item := range object.Items {
		if a.result.ObjectKeys >= MaxNodes {
			a.stopWalk()
		}
		a.result.ObjectKeys++
		name, known := keyName(item.KeyExpr)
		if !known {
			a.refuse("computed_object_key")
			continue
		}
		if seen[name] {
			a.refuse("duplicate_object_key")
		}
		seen[name] = true
		if routingName(name) {
			a.refuse("routing_object_key")
		}
		if name == "alias" || name == "configuration_aliases" {
			a.refuse("alias_declaration")
		}
	}
}

// Traversals stay opaque: never evaluate their source or steps. Only a
// well-formed absolute root followed by attributes, or a nonempty relative
// sequence of attributes, is within the prototype predicate.
func attributeOnlyTraversal(steps hcl.Traversal, absolute bool) bool {
	if len(steps) == 0 {
		return false
	}
	for index, step := range steps {
		switch value := step.(type) {
		case hcl.TraverseRoot:
			if !absolute || index != 0 || value.Name == "" {
				return false
			}
		case hcl.TraverseAttr:
			if absolute && index == 0 || value.Name == "" {
				return false
			}
		default:
			// Includes TraverseIndex, TraverseSplat, nil and future step kinds.
			return false
		}
	}
	return true
}


// A unique, nonzero-sized private signal stops the upstream recursive walk.
// Only this exact identity is recovered; all unexpected panics propagate.
type walkStop struct{ marker byte }

var boundedWalkStop = &walkStop{marker: 1}

func (a *analysis) stopWalk() {
	a.truncated = true
	a.refuse("bounds_refused")
	panic(boundedWalkStop)
}

func (a *analysis) walk(node hclsyntax.Node) {
	defer func() {
		if value := recover(); value != nil {
			if stop, ok := value.(*walkStop); !ok || stop != boundedWalkStop {
				panic(value)
			}
		}
	}()
	hclsyntax.Walk(node, a)
}

func (a *analysis) Enter(node hclsyntax.Node) hcl.Diagnostics {
	if a.depth >= MaxASTDepth || a.result.Nodes >= MaxNodes {
		a.stopWalk()
	}
	a.depth++
	a.result.Nodes++
	switch value := node.(type) {
	case *hclsyntax.Block:
		a.blocks = append(a.blocks, value.Type)
		if value.Type == "provider" {
			a.refuse("provider_block")
		} else if value.Type == "dynamic" || value.Type == "provider_meta" || routingName(value.Type) {
			a.refuse("unsupported_structure")
		}
	case *hclsyntax.Attribute:
		parent := ""
		if len(a.blocks) != 0 {
			parent = a.blocks[len(a.blocks)-1]
		}
		switch value.Name {
		case "provider":
			if parent == "resource" || parent == "data" {
				a.refuse("provider_selector")
			} else {
				a.refuse("routing_attribute")
			}
		case "providers":
			if parent == "module" {
				a.refuse("provider_mapping")
			} else {
				a.refuse("routing_attribute")
			}
		case "alias", "configuration_aliases":
			a.refuse("alias_declaration")
		}
	case *hclsyntax.ObjectConsExpr:
		a.checkObject(value)
	}
	if expr, ok := node.(hclsyntax.Expression); ok {
		switch value := expr.(type) {
		case *hclsyntax.ScopeTraversalExpr:
			if !attributeOnlyTraversal(value.Traversal, true) {
				a.refuse("unsupported_expression")
			}
		case *hclsyntax.RelativeTraversalExpr:
			if !attributeOnlyTraversal(value.Traversal, false) {
				a.refuse("unsupported_expression")
			}
		case *hclsyntax.LiteralValueExpr, *hclsyntax.TupleConsExpr,
			*hclsyntax.ObjectConsExpr, *hclsyntax.ObjectConsKeyExpr, *hclsyntax.ParenthesesExpr:
		case *hclsyntax.TemplateExpr:
			if !value.IsStringLiteral() {
				a.refuse("unsupported_expression")
			}
		default:
			// Computation, interpolation, comprehensions, indexing, splats,
			// operators and future expression kinds are outside this predicate.
			a.refuse("unsupported_expression")
		}
	}
	return nil
}

func (a *analysis) Exit(node hclsyntax.Node) hcl.Diagnostics {
	if _, ok := node.(*hclsyntax.Block); ok {
		a.blocks = a.blocks[:len(a.blocks)-1]
	}
	a.depth--
	return nil
}
