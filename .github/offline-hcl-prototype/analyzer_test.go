package hclprototype

import (
	"bytes"
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

type example struct {
	name     string
	source   string
	category string
}

var examples = []example{
	{"line comment", "# provider providers alias configuration_aliases\nlocals { safe = 1 }\n", ""},
	{"slash comment", "// provider \"azapi\" { alias = \"x\" }\nlocals { safe = 1 }\n", ""},
	{"block comment", "/* provider = azapi.x\n providers = {} */\nlocals { safe = 1 }\n", ""},
	{"plain string", `locals { text = "provider providers alias configuration_aliases" }`, ""},
	{"escaped string", `locals { text = "provider \"azapi\" { alias = \"x\" }" }`, ""},
	{"escaped interpolation inert", `locals { text = "$${provider} %%{if providers}" }`, ""},
	{"ordinary heredoc", "locals {\n text = <<EOF\nprovider \"azapi\" { alias = \"x\" }\nproviders = {}\nEOF\n}\n", ""},
	{"indented heredoc", "locals {\n text = <<-EOF\n  provider = azapi.x\n  configuration_aliases = []\n  EOF\n}\n", ""},
	{"heredoc delimiter inside text", "locals {\n text = <<EOF\nEOF_is_not_a_terminator\nprovider = azapi.x\nEOF\n}\n", ""},
	{"comment after terminator", "locals {\n text = <<EOF\nprovider = azapi.x\nEOF\n # providers = {}\n safe = 1\n}\n", ""},
	{"comment-only nonempty", "# provider syntax is inert\n", ""},
	{"CRLF heredoc", "locals {\r\n text = <<EOF\r\nprovider = azapi.x\r\nEOF\r\n}\r\n", ""},
	{"unicode string", `locals { text = "provider \u0070rovider \U00000070rovider" }`, ""},
	{"required providers native", "terraform {\n required_providers {\n azapi = { source = \"Azure/azapi\", version = \"2.12.0\" }\n }\n}\n", ""},
	{"ordinary resource", "resource \"azapi_resource\" \"x\" {\n type = \"Example/type\"\n location = var.location\n body = { name = \"example\", enabled = true }\n}\n", ""},
	{"ordinary module", "module \"x\" {\n source = \"./synthetic\"\n settings = { safe = \"provider\" }\n}\n", ""},
	{"provider-prefix names", "locals {\n provider_note = \"inert\"\n settings = { providers_note = \"inert\", required_providers = {} }\n}\n", ""},
	{"literal quoted object key", `locals { settings = { "safe" = 1 } }`, ""},
	{"literal parenthesized key", `locals { settings = { ("safe") = 1 } }`, ""},
	{"double parenthesized key", `locals { settings = { (("safe")) = 1 } }`, ""},
	{"bare special keyword key", `locals { settings = { true = 1, false = 2, null = 3 } }`, ""},
	{"nested objects and tuples", `locals { settings = [{ safe = { child = ["provider"] } }] }`, ""},
	{"ordinary nested block", "resource \"x\" \"y\" {\n settings {\n value = { safe = \"provider\" }\n }\n}\n", ""},
	{"bare provider block", `provider "azapi" {}`, "provider_block"},
	{"provider block with alias", `provider "azapi" { alias = "bypass" }`, "provider_block"},
	{"nested provider block", "wrapper {\n provider \"azapi\" {}\n}\n", "provider_block"},
	{"resource selector", `resource "azapi_resource" "x" { provider = azapi.bypass }`, "provider_selector"},
	{"data selector", `data "azapi_client_config" "x" { provider = azapi.bypass }`, "provider_selector"},
	{"selector with comment", "resource \"azapi_resource\" \"x\" {\n provider /* inert */ = azapi.bypass\n}\n", "provider_selector"},
	{"nested selector", "resource \"x\" \"y\" {\n lifecycle {\n provider = azapi.bypass\n }\n}\n", "routing_attribute"},
	{"module mapping", "module \"x\" {\n source = \"./synthetic\"\n providers = { azapi = azapi.bypass }\n}\n", "provider_mapping"},
	{"alias attribute", `locals { alias = "bypass" }`, "alias_declaration"},
	{"aliases attribute", "terraform {\n required_providers {\n azapi = {\n source = \"Azure/azapi\"\n configuration_aliases = [azapi.bypass]\n }\n }\n}\n", "alias_declaration"},
	{"root provider attribute", `provider = azapi.bypass`, "routing_attribute"},
	{"root providers attribute", `providers = { azapi = azapi.bypass }`, "routing_attribute"},
	{"bare routing object key", `locals { settings = { provider = "value" } }`, "routing_object_key"},
	{"quoted routing object key", `locals { settings = { "providers" = {} } }`, "routing_object_key"},
	{"unicode escaped routing key", `locals { settings = { "prov\u0069der" = "x" } }`, "routing_object_key"},
	{"long unicode escaped key", `locals { settings = { "\U00000070rovider" = "x" } }`, "routing_object_key"},
	{"parenthesized quoted routing key", `locals { settings = { ("provider") = "x" } }`, "routing_object_key"},
	{"double parenthesized encoded key", `locals { settings = { (("\u0070roviders")) = {} } }`, "routing_object_key"},
	{"nested routing object", `locals { settings = [{ safe = { provider = "x" } }] }`, "routing_object_key"},
	{"alias object key", `locals { settings = { alias = "x" } }`, "alias_declaration"},
	{"encoded aliases object key", `locals { settings = { "configuration_\u0061liases" = [] } }`, "alias_declaration"},
	{"parenthesized variable key", `locals { settings = { (provider) = "x" } }`, "computed_object_key"},
	{"traversal key", `locals { settings = { var.key = "x" } }`, "computed_object_key"},
	{"parenthesized traversal key", `locals { settings = { (var.key) = "x" } }`, "computed_object_key"},
	{"function computed key", `locals { settings = { (lower("PROVIDER")) = "x" } }`, "computed_object_key"},
	{"concat computed key", `locals { settings = { ("prov" + "ider") = "x" } }`, "computed_object_key"},
	{"constant interpolated key", `locals { settings = { "${"provider"}" = "x" } }`, "computed_object_key"},
	{"split interpolated key", `locals { settings = { "prov${"ider"}" = "x" } }`, "computed_object_key"},
	{"variable interpolated key", `locals { settings = { "${var.key}" = "x" } }`, "computed_object_key"},
	{"numeric object key", `locals { settings = { (1) = "x" } }`, "computed_object_key"},
	{"conditional object key", `locals { settings = { (true ? "provider" : "safe") = "x" } }`, "computed_object_key"},
	{"heredoc object key retains newline", "locals {\n settings = {\n (<<EOF\nprovider\nEOF\n ) = \"x\"\n }\n}\n", ""},
	{"duplicate bare object key", `locals { settings = { safe = 1, safe = 2 } }`, "duplicate_object_key"},
	{"duplicate decoded object key", `locals { settings = { safe = 1, "\u0073afe" = 2 } }`, "duplicate_object_key"},
	{"duplicate parenthesized object key", `locals { settings = { "safe" = 1, ("safe") = 2 } }`, "duplicate_object_key"},
	{"duplicate Unicode normalized key", "locals { settings = { caf\u00e9 = 1, \"cafe\\u0301\" = 2 } }", "duplicate_object_key"},
	{"duplicate body attributes", "locals {\n safe = 1\n safe = 2\n}\n", "syntax_refused"},
	{"duplicate routing attributes", "resource \"x\" \"y\" {\n provider = azapi.a\n provider = azapi.b\n}\n", "syntax_refused"},
	{"dynamic block", "resource \"x\" \"y\" {\n dynamic \"settings\" {\n for_each = var.items\n content { safe = 1 }\n }\n}\n", "unsupported_structure"},
	{"dynamic provider label", "wrapper {\n dynamic \"provider\" {\n for_each = []\n content {}\n }\n}\n", "unsupported_structure"},
	{"provider meta", `provider_meta "azapi" {}`, "unsupported_structure"},
	{"providers block", "wrapper {\n providers {}\n}\n", "unsupported_structure"},
	{"function value", `locals { value = jsondecode("{\"provider\":{}}") }`, "unsupported_expression"},
	{"object comprehension", `locals { value = { for k, v in var.items : k => v } }`, "unsupported_expression"},
	{"tuple comprehension", `locals { value = [for v in var.items : v] }`, "unsupported_expression"},
	{"splat", `locals { value = var.items[*].name }`, "unsupported_expression"},
	{"index expression", `locals { value = var.items[var.key] }`, "unsupported_expression"},
	{"conditional expression", `locals { value = true ? "provider" : "safe" }`, "unsupported_expression"},
	{"binary operator", `locals { value = 1 + 2 }`, "unsupported_expression"},
	{"unary operator", `locals { value = !true }`, "unsupported_expression"},
	{"constant interpolation value", `locals { value = "${"provider"}" }`, "unsupported_expression"},
	{"variable interpolation value", `locals { value = "${var.text}" }`, "unsupported_expression"},
	{"interpolated heredoc", "locals {\n value = <<EOF\n${var.text}\nprovider = azapi.x\nEOF\n}\n", "unsupported_expression"},
	{"template control heredoc", "locals {\n value = <<EOF\n%{if true}provider%{endif}\nEOF\n}\n", "unsupported_expression"},
	{"routing attribute after heredoc", "locals {\n text = <<EOF\nprovider is inert here\nEOF\n provider = azapi.x\n}\n", "routing_attribute"},
	{"mapping after indented heredoc", "module \"x\" {\n source = \"./synthetic\"\n text = <<-EOF\n  provider is inert here\n  EOF\n providers = { azapi = azapi.x }\n}\n", "provider_mapping"},
	{"provider block after heredoc", "locals {\n text = <<EOF\nprovider is inert here\nEOF\n}\nprovider \"azapi\" {}\n", "provider_block"},
	{"bad trailing heredoc tokens", "locals {\n text = <<EOF\nprovider is inert here\nEOF provider = azapi.x\n}\n", "syntax_refused"},
	{"unclosed heredoc", "locals {\n text = <<EOF\nprovider = azapi.x\n}\n", "syntax_refused"},
	{"unclosed body", "locals { safe = 1", "syntax_refused"},
	{"unclosed comment", "/* provider is not a closed comment", "syntax_refused"},
	{"bad string escape", `locals { text = "\q" }`, "syntax_refused"},
	{"malformed body selector", `resource "x" "y" { "provider" = azapi.x }`, "syntax_refused"},
	{"malformed expression", `locals { safe = @ }`, "syntax_refused"},
	{"NUL", "locals { safe = 1 }\x00", "syntax_refused"},
}

func hasCategory(result Result, category string) bool {
	for _, item := range result.Categories {
		if item == category {
			return true
		}
	}
	return false
}

func TestSyntheticExamples(t *testing.T) {
	for _, test := range examples {
		t.Run(test.name, func(t *testing.T) {
			got := Analyze(NativeHCL, []byte(test.source))
			if test.category == "" {
				if got.Outcome != "accepted_predicate" || len(got.Categories) != 0 {
					t.Fatalf("expected accepted predicate, got %+v", got)
				}
			} else if got.Outcome != "refused" || !hasCategory(got, test.category) {
				t.Fatalf("expected refusal category %s, got %+v", test.category, got)
			}
			if repeated := Analyze(NativeHCL, []byte(test.source)); !reflect.DeepEqual(got, repeated) {
				t.Fatal("nondeterministic fixed result")
			}
		})
	}
}

func TestFormatEncodingAndBounds(t *testing.T) {
	tests := []struct {
		name     string
		format   string
		source   []byte
		category string
	}{
		{"JSON unsupported", "terraform-json", []byte(`{"provider":{}}`), "format_refused"},
		{"unknown format", "unknown", []byte("locals {}"), "format_refused"},
		{"empty bytes", NativeHCL, nil, "bounds_refused"},
		{"invalid UTF8", NativeHCL, []byte{0xff}, "encoding_refused"},
		{"over byte bound", NativeHCL, bytes.Repeat([]byte(" "), MaxBytes+1), "bounds_refused"},
		{"over token bound", NativeHCL, []byte(strings.Repeat("\n", MaxTokens+1)), "bounds_refused"},
		{"over parenthesis depth", NativeHCL, []byte("locals { value = " + strings.Repeat("(", MaxLexDepth+1) + "1" + strings.Repeat(")", MaxLexDepth+1) + " }"), "bounds_refused"},
		{"over object depth", NativeHCL, []byte("locals { value = " + strings.Repeat("{ safe = ", MaxLexDepth+1) + "1" + strings.Repeat(" }", MaxLexDepth+1) + " }"), "bounds_refused"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := Analyze(test.format, test.source)
			if got.Outcome != "refused" || !hasCategory(got, test.category) {
				t.Fatalf("expected %s, got %+v", test.category, got)
			}
		})
	}
	atByteBound := []byte("#" + strings.Repeat("x", MaxBytes-2) + "\n")
	if got := Analyze(NativeHCL, atByteBound); got.Outcome != "accepted_predicate" {
		t.Fatalf("exact byte boundary unexpectedly refused: %+v", got)
	}
	atTokenBound := []byte(strings.Repeat("\n", MaxTokens-1))
	if got := Analyze(NativeHCL, atTokenBound); got.Outcome != "accepted_predicate" {
		t.Fatalf("exact token boundary unexpectedly refused: %+v", got)
	}
	atLexDepth := []byte("locals { value = " + strings.Repeat("(", MaxLexDepth-1) +
		"1" + strings.Repeat(")", MaxLexDepth-1) + " }")
	if got := Analyze(NativeHCL, atLexDepth); got.Outcome != "accepted_predicate" {
		t.Fatalf("exact lexical depth boundary unexpectedly refused: %+v", got)
	}
}

func TestFixedOutputRedaction(t *testing.T) {
	for _, source := range []string{
		`provider "DO_NOT_LEAK" {}`,
		`locals { value = { ("DO_NOT_LEAK${var.secret}") = 1 } }`,
		"locals { value = \"DO_NOT_LEAK",
	} {
		result := Analyze(NativeHCL, []byte(source))
		encoded, err := json.Marshal(result)
		if err != nil {
			t.Fatal("fixed result cannot be serialized")
		}
		if bytes.Contains(encoded, []byte("DO_NOT_LEAK")) || bytes.Contains(encoded, []byte("secret")) ||
			bytes.Contains(encoded, []byte("synthetic.tf")) {
			t.Fatal("source or diagnostic escaped the fixed result")
		}
	}
}

func TestAllStructuralNodesAreVisited(t *testing.T) {
	source := `locals { value = [{ safe = { "provider" = "x" } }] }
resource "x" "y" {
 settings {
  alias = "x"
 }
}
provider "azapi" {}
`
	got := Analyze(NativeHCL, []byte(source))
	for _, category := range []string{"routing_object_key", "alias_declaration", "provider_block"} {
		if !hasCategory(got, category) {
			t.Fatalf("missing category %s after an earlier refusal", category)
		}
	}
	if got.Objects != 2 || got.ObjectKeys != 2 || got.Nodes == 0 {
		t.Fatalf("unexpected bounded visitation counts: %+v", got)
	}
}

func TestParenthesizedBareKeyIsNotLiteral(t *testing.T) {
	got := Analyze(NativeHCL, []byte(`locals { value = { (provider) = 1 } }`))
	if !hasCategory(got, "computed_object_key") || hasCategory(got, "routing_object_key") {
		t.Fatalf("HCL ForceNonLiteral semantics were lost: %+v", got)
	}
}

func TestExactSmallObjectCounts(t *testing.T) {
	got := Analyze(NativeHCL, []byte(`locals { value = { safe = 1, "other" = 2 } }`))
	if got.Outcome != "accepted_predicate" || got.Objects != 1 || got.ObjectKeys != 2 {
		t.Fatalf("unexpected fixed result: %+v", got)
	}
}

func FuzzAnalyze(f *testing.F) {
	for _, seed := range examples {
		f.Add([]byte(seed.source))
	}
	f.Add([]byte{0xff})
	f.Add([]byte{})
	allowed := map[string]bool{
		"format_refused": true, "bounds_refused": true, "encoding_refused": true,
		"syntax_refused": true, "unsupported_structure": true, "unsupported_expression": true,
		"provider_block": true, "provider_selector": true, "provider_mapping": true,
		"routing_attribute": true, "alias_declaration": true, "routing_object_key": true,
		"computed_object_key": true, "duplicate_object_key": true,
	}
	f.Fuzz(func(t *testing.T, source []byte) {
		result := Analyze(NativeHCL, source)
		if result.Outcome != "accepted_predicate" && result.Outcome != "refused" {
			t.Fatal("invalid fixed outcome")
		}
		if (result.Outcome == "accepted_predicate") != (len(result.Categories) == 0) {
			t.Fatal("success-shaped refusal")
		}
		for _, category := range result.Categories {
			if !allowed[category] {
				t.Fatal("unbounded category")
			}
		}
		for _, count := range []int{result.Nodes, result.Objects, result.ObjectKeys} {
			if count < 0 || count > MaxNodes {
				t.Fatal("unbounded result count")
			}
		}
		if repeated := Analyze(NativeHCL, source); !reflect.DeepEqual(result, repeated) {
			t.Fatal("nondeterministic result")
		}
	})
}

func TestSyntheticCaseInventory(t *testing.T) {
	positive, negative := 0, 0
	names := make(map[string]bool)
	for _, test := range examples {
		if names[test.name] {
			t.Fatal("duplicate synthetic case name")
		}
		names[test.name] = true
		if test.category == "" {
			positive++
		} else {
			negative++
		}
	}
	if positive < 20 || negative < 50 {
		t.Fatal("synthetic category coverage was reduced")
	}
	t.Log(fmt.Sprintf("synthetic_positive=%d synthetic_negative=%d", positive, negative))
}
