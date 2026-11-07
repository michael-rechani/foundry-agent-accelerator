package hclprototype

import (
	"reflect"
	"testing"

	"github.com/hashicorp/hcl/v2/hclsyntax"
	"github.com/zclconf/go-cty/cty"
)

func boundedState() *analysis {
	return &analysis{categories: make(map[string]bool)}
}

func TestBoundedWalkDepthBoundary(t *testing.T) {
	for _, depth := range []int{MaxASTDepth - 1, MaxASTDepth, MaxASTDepth + 1} {
		var root hclsyntax.Expression = &hclsyntax.LiteralValueExpr{Val: cty.True}
		for i := 1; i < depth; i++ {
			root = &hclsyntax.ParenthesesExpr{Expression: root}
		}
		state := boundedState()
		state.walk(root)
		result := state.finish()
		if depth <= MaxASTDepth {
			if result.Outcome != "accepted_predicate" || len(result.Categories) != 0 || result.Nodes != depth || state.depth != 0 {
				t.Fatalf("within-depth decision changed: %+v", result)
			}
		} else if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories, []string{"bounds_refused"}) || result.Nodes != MaxASTDepth {
			t.Fatalf("depth overflow did not stop before excess processing: %+v", result)
		}
	}
}

func TestBoundedWalkNodeBoundary(t *testing.T) {
	for _, nodes := range []int{MaxNodes - 1, MaxNodes, MaxNodes + 1} {
		root := &hclsyntax.TupleConsExpr{}
		for i := 1; i < nodes; i++ {
			root.Exprs = append(root.Exprs, &hclsyntax.LiteralValueExpr{Val: cty.True})
		}
		state := boundedState()
		state.walk(root)
		result := state.finish()
		if nodes <= MaxNodes {
			if result.Outcome != "accepted_predicate" || len(result.Categories) != 0 || result.Nodes != nodes || state.depth != 0 {
				t.Fatalf("within-node decision changed: %+v", result)
			}
		} else if result.Outcome != "refused" || !reflect.DeepEqual(result.Categories, []string{"bounds_refused"}) || result.Nodes != MaxNodes {
			t.Fatalf("node overflow did not stop before excess processing: %+v", result)
		}
	}
}

func TestBoundedWalkDoesNotVisitWideTail(t *testing.T) {
	body := &hclsyntax.Body{}
	for i := 0; i < MaxNodes; i++ {
		body.Blocks = append(body.Blocks, &hclsyntax.Block{Type: "ordinary", Body: &hclsyntax.Body{}})
	}
	body.Blocks = append(body.Blocks, &hclsyntax.Block{Type: "provider", Body: &hclsyntax.Body{}})
	state := boundedState()
	state.walk(body)
	result := state.finish()
	if result.Outcome != "refused" || result.Nodes != MaxNodes || !reflect.DeepEqual(result.Categories, []string{"bounds_refused"}) {
		t.Fatalf("wide tail visited or truncation accepted: %+v", result)
	}
	// The last tail is deliberately invalid: visiting it would panic. Its
	// absence of panic separately proves the walker did not descend that far.
	body.Blocks = append(body.Blocks, nil)
	state = boundedState()
	state.walk(body)
	if state.finish().Outcome != "refused" {
		t.Fatal("truncated invalid tail accepted")
	}
}

func TestBoundedObjectKeyIteration(t *testing.T) {
	for _, keys := range []int{MaxNodes - 1, MaxNodes, MaxNodes + 1} {
		object := &hclsyntax.ObjectConsExpr{}
		for i := 0; i < keys; i++ {
			object.Items = append(object.Items, hclsyntax.ObjectConsItem{
				KeyExpr: &hclsyntax.ObjectConsKeyExpr{
					Wrapped: &hclsyntax.LiteralValueExpr{Val: cty.StringVal("ordinary")},
				},
				ValueExpr: &hclsyntax.LiteralValueExpr{Val: cty.True},
			})
		}
		state := boundedState()
		if keys > MaxNodes {
			object.Items[keys-1].KeyExpr = &hclsyntax.ObjectConsKeyExpr{
				Wrapped: &hclsyntax.LiteralValueExpr{Val: cty.StringVal("provider")},
			}
			state.walk(object)
		} else {
			// Isolate the visitor's eager key loop from the later node budget.
			state.checkObject(object)
		}
		result := state.finish()
		want := keys
		if want > MaxNodes {
			want = MaxNodes
		}
		if result.ObjectKeys != want || !hasCategory(result, "duplicate_object_key") {
			t.Fatalf("key-loop boundary changed: %+v", result)
		}
		if keys > MaxNodes && (result.Outcome != "refused" || !hasCategory(result, "bounds_refused") || hasCategory(result, "routing_object_key")) {
			t.Fatalf("key tail visited or truncation accepted: %+v", result)
		}
	}
}

func TestBoundedWalkRepanicsUnexpectedFailure(t *testing.T) {
	defer func() {
		value := recover()
		if value == nil {
			t.Fatal("unexpected upstream panic was swallowed")
		}
		if stop, ok := value.(*walkStop); ok && stop == boundedWalkStop {
			t.Fatal("unexpected panic replaced with internal stop")
		}
	}()
	boundedState().walk(nil)
}
