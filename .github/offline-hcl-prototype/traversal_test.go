package hclprototype

import (
	"testing"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/hclsyntax"
)

func TestParsedTraversalIndexRefusals(t *testing.T) {
	tests := []struct {
		name       string
		expression string
		absolute   bool
	}{
		{"scope numeric literal", `var.items[0]`, true},
		{"scope quoted string literal", `var.items["key"]`, true},
		{"scope escaped string literal", `var.items["\u006bey"]`, true},
		{"scope legacy numeric", `var.items.0`, true},
		{"scope chained attribute and index", `var.items[0].child["key"].name`, true},
		{"scope after attribute chain", `var.parent.items[0]`, true},
		{"relative numeric on parentheses", `(var.items)[0]`, false},
		{"relative string on object", `({items = {key = 1}}).items["key"]`, false},
		{"relative numeric on tuple", `([1, 2])[0]`, false},
		{"relative legacy numeric", `(var.items).0`, false},
		{"relative chained", `(var.items)[0].child["key"].name`, false},
		{"relative indexed literal string", `("text")[0]`, false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			source := []byte("locals { value = " + test.expression + " }")
			file, diagnostics := hclsyntax.ParseConfig(source, "synthetic.tf", hcl.InitialPos)
			if len(diagnostics) != 0 || file == nil {
				t.Fatal("synthetic case did not parse without diagnostics")
			}
			body := file.Body.(*hclsyntax.Body)
			expr := body.Blocks[0].Body.Attributes["value"].Expr
			found := false
			hclsyntax.VisitAll(expr, func(node hclsyntax.Node) hcl.Diagnostics {
				var steps hcl.Traversal
				switch traversal := node.(type) {
				case *hclsyntax.ScopeTraversalExpr:
					if test.absolute {
						steps = traversal.Traversal
					}
				case *hclsyntax.RelativeTraversalExpr:
					if !test.absolute {
						steps = traversal.Traversal
					}
				}
				for _, step := range steps {
					if _, ok := step.(hcl.TraverseIndex); ok {
						found = true
					}
				}
				return nil
			})
			if !found {
				t.Fatal("case did not exercise the expected parser traversal with an index step")
			}
			result := Analyze(NativeHCL, source)
			if result.Outcome != "refused" || !hasCategory(result, "unsupported_expression") {
				t.Fatalf("indexed traversal was not refused: %+v", result)
			}
		})
	}
}

func TestNonIndexTraversalsAndInertText(t *testing.T) {
	tests := []string{
		`var`,
		`var.items`,
		`var.items.child.name`,
		`(var.items).child.name`,
		`({items = {child = 1}}).items.child`,
		`"var.items[0]"`,
	}
	for _, expression := range tests {
		t.Run(expression, func(t *testing.T) {
			result := Analyze(NativeHCL, []byte("locals { value = "+expression+" }"))
			if result.Outcome != "accepted_predicate" || len(result.Categories) != 0 {
				t.Fatalf("ordinary non-index expression refused: %+v", result)
			}
		})
	}
}

func TestNestedIndexRefusalDoesNotSkipOtherNodes(t *testing.T) {
	source := []byte(`locals { value = { safe = var.items[0] } }
provider "azapi" {}
`)
	result := Analyze(NativeHCL, source)
	if result.Outcome != "refused" || !hasCategory(result, "unsupported_expression") ||
		!hasCategory(result, "provider_block") {
		t.Fatalf("nested index or unrelated routing block not reported: %+v", result)
	}
}

func TestTraversalStepAllowlistFailsClosed(t *testing.T) {
	root := hcl.TraverseRoot{Name: "var"}
	attr := hcl.TraverseAttr{Name: "items"}
	unknown := hcl.TraverseSplat{}
	tests := []struct {
		name     string
		steps    hcl.Traversal
		absolute bool
		want     bool
	}{
		{"absolute root", hcl.Traversal{root}, true, true},
		{"absolute root and attributes", hcl.Traversal{root, attr, attr}, true, true},
		{"relative attributes", hcl.Traversal{attr, attr}, false, true},
		{"empty absolute", nil, true, false},
		{"empty relative", nil, false, false},
		{"absolute lacks root", hcl.Traversal{attr}, true, false},
		{"root in relative", hcl.Traversal{root}, false, false},
		{"root after absolute root", hcl.Traversal{root, root}, true, false},
		{"root after relative attribute", hcl.Traversal{attr, root}, false, false},
		{"unknown absolute step", hcl.Traversal{root, unknown}, true, false},
		{"unknown relative step", hcl.Traversal{attr, unknown}, false, false},
		{"index absolute step", hcl.Traversal{root, hcl.TraverseIndex{}}, true, false},
		{"index relative step", hcl.Traversal{hcl.TraverseIndex{}}, false, false},
		{"nil absolute step", hcl.Traversal{root, nil}, true, false},
		{"empty root name", hcl.Traversal{hcl.TraverseRoot{}}, true, false},
		{"empty attr name", hcl.Traversal{root, hcl.TraverseAttr{}}, true, false},
		{"pointer step not allowlisted", hcl.Traversal{root, &attr}, true, false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := attributeOnlyTraversal(test.steps, test.absolute); got != test.want {
				t.Fatalf("allowlist returned %t; want %t", got, test.want)
			}
			var node hclsyntax.Node
			if test.absolute {
				node = &hclsyntax.ScopeTraversalExpr{Traversal: test.steps}
			} else {
				node = &hclsyntax.RelativeTraversalExpr{Traversal: test.steps}
			}
			state := &analysis{categories: make(map[string]bool)}
			state.Enter(node)
			state.Exit(node)
			result := state.finish()
			if hasCategory(result, "unsupported_expression") == test.want {
				t.Fatalf("AST visitor did not enforce allowlist: %+v", result)
			}
		})
	}
}
