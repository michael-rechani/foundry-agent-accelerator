package hclprototype

import (
	"fmt"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/hclsyntax"
)

// These synthetic cases exercise parsing paths that can do substantial work
// despite small token counts. Durations are observations, not time bounds.
func TestFuzzDeadlineStress(t *testing.T) {
	const prefix = "locals { value = "
	const suffix = " }"
	var object strings.Builder
	object.WriteString("locals { value = {\n")
	for i := 0; i < 1200; i++ {
		fmt.Fprintf(&object, "key%04d = 1\n", i)
	}
	object.WriteString("} }")

	tests := []struct {
		name   string
		source string
	}{
		{"decimal_8192_digits", prefix + strings.Repeat("9", 8192) + suffix},
		{"decimal_32768_digits", prefix + strings.Repeat("9", 32768) + suffix},
		{"decimal_max_bytes", prefix + strings.Repeat("9", MaxBytes-len(prefix)-len(suffix)) + suffix},
		{"large_decimal_exponent", prefix + "1e1000000" + suffix},
		{"long_normalized_string", prefix + `"` + strings.Repeat("e\u0301", 20000) + `"` + suffix},
		{"long_attribute_traversal", prefix + "var" + strings.Repeat(".field", 4000) + suffix},
		{"many_object_keys", object.String()},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			source := []byte(test.source)
			if len(source) > MaxBytes {
				t.Fatal("synthetic case exceeds byte limit")
			}
			tokens, diagnostics := hclsyntax.LexConfig(source, "synthetic.tf", hcl.InitialPos)
			if len(diagnostics) != 0 || len(tokens) > MaxTokens {
				t.Fatal("synthetic case does not lex within token limit")
			}
			start := time.Now()
			file, diagnostics := hclsyntax.ParseConfig(source, "synthetic.tf", hcl.InitialPos)
			parseDuration := time.Since(start)
			if len(diagnostics) != 0 || file == nil {
				t.Fatal("synthetic case did not parse")
			}
			start = time.Now()
			result := Analyze(NativeHCL, source)
			firstDuration := time.Since(start)
			start = time.Now()
			repeated := Analyze(NativeHCL, source)
			secondDuration := time.Since(start)
			if result.Outcome != "accepted_predicate" || len(result.Categories) != 0 {
				t.Fatalf("unexpected fixed outcome or category: %+v", result)
			}
			if !reflect.DeepEqual(result, repeated) {
				t.Fatal("synthetic case produced nondeterministic results")
			}
			t.Logf("bytes=%d tokens=%d nodes=%d parse=%s analyze_first=%s analyze_second=%s",
				len(source), len(tokens), result.Nodes, parseDuration, firstDuration, secondDuration)
		})
	}
}

// This control uses the same Go fuzz machinery without invoking the analyzer.
func FuzzNoopControl(f *testing.F) {
	f.Add([]byte("synthetic"))
	f.Fuzz(func(t *testing.T, source []byte) {
		_ = len(source)
	})
}
