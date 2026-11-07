# Isolated offline native-HCL syntax prototype

This is a **synthetic-input-only prototype**, not a replacement for the existing
conservative scanner. It is not connected to a runtime gate, file reader,
dependency-closure scanner, diagnostic, plan, apply, deployment, or provider
execution. Its result cannot authorize those operations or establish absence of
bypasses or source trust. No public dependency artifact was inspected again.

The package in `.github/offline-hcl-prototype` exposes
`Analyze(format string, source []byte) Result`. Only `native-hcl` is accepted as
the format. The prototype provides no filesystem input or command-line adapter.
All validation inputs were synthetic, checked-in examples or generated fuzz bytes.
Terraform JSON is deliberately unsupported; the existing JSON and conservative
HCL scanners are untouched.

## Exact limited predicate

`accepted_predicate` means only that the supplied bounded UTF-8 byte sequence:

1. Parsed as native HCL with **no parser or lexer diagnostics**.
2. Contained no block whose type is exactly `provider`, anywhere in the AST.
3. Contained no body attribute named exactly `provider`, `providers`, `alias`,
   or `configuration_aliases`, anywhere in the AST.
4. Had only statically literal object-constructor keys, with no duplicate decoded
   keys and no key named exactly `provider`, `providers`, `alias`, or
   `configuration_aliases`.
5. Contained no `dynamic`, `provider_meta`, or other routing-named block, and no
   expression outside the explicitly supported AST subset.

Names are compared exactly, case-sensitively, without trimming literal strings.
This is not Terraform schema validation. Ordinary native-HCL block types and
labels are not interpreted as Terraform schemas. `required_providers`
declarations without aliases are intentionally permitted; local provider names,
source addresses, versions and bindings are not resolved.

Comments and literal string/heredoc contents are inert to this predicate.
The real HCL lexer/parser, rather than regex, determines string escapes, heredoc
boundaries, nested syntax and structural tokens after heredoc termination.
Literal `$${...}` and `%%{...}` escapes remain text. A heredoc used as a literal
object key retains its newline: `"provider\n"` is a different key from `"provider"`.
Tokens after a valid heredoc terminator are still parsed and visited; malformed
trailing tokens are refused.

Object keys follow the pinned HCL AST's `ObjectConsKeyExpr` semantics. Bare
keywords are literal keys only when `ForceNonLiteral` is false. Quoted Unicode
escapes are decoded by HCL; literal keys are normalized consistently with cty
strings before duplicate comparisons. Parenthesized quoted literals remain
literal. In contrast, `(provider)` is a variable reference, not the literal key
`provider`, and is refused as a computed key. Traversal, function, numeric,
conditional and interpolated keys are refused rather than evaluated, even if a
full evaluator might determine a constant result.

Supported expression nodes are literal values, scope/relative traversals,
tuples, object constructors and their key wrappers, parentheses, and
single-literal `TemplateExpr` nodes. Traversals are opaque references, not
evaluated values, but every traversal step must pass the explicit attribute-only
allowlist described below. All other expression types are refused, including function
calls, operators, indexing, splats, comprehensions, template controls, and all
interpolation, including constant interpolation. Nested expressions/blocks and
every object constructor are visited; a routing refusal does not end AST
visitation early. Body duplicate attributes are rejected by the parser before
analysis; duplicate object keys are rejected by the prototype.

No expression `Value` method, evaluation context, external function, module
resolution or provider is invoked. cty is used only to inspect and normalize
parser-produced literal strings.

## Fixed failures and bounds

The result contains only `Outcome`, sorted fixed `Categories`, and bounded
`Nodes`, `Objects`, and `ObjectKeys` integer counts. Source text, labels,
filenames and raw parser diagnostics are never included in it.

Refusal categories are `format_refused`, `bounds_refused`, `encoding_refused`,
`syntax_refused`, `unsupported_structure`, `unsupported_expression`,
`provider_block`, `provider_selector`, `provider_mapping`, `routing_attribute`,
`alias_declaration`, `routing_object_key`, `computed_object_key`, and
`duplicate_object_key`. `provider_selector` identifies a direct resource/data
attribute; `provider_mapping` identifies a direct module mapping. Other matching
attributes are still refused.

Inputs must be nonempty and at most 65536 bytes. The pinned lexer is used before
parsing to bound token count to 8192 and lexical nesting to 32. Defensive AST
limits are 16384 nodes and depth 128; reported counts are capped. Tests measure
exact byte/token/lexical-depth boundaries and over-bound refusals.
These are resource bounds, not a sandbox or proof of parser safety.

## Pinned dependency and evidence identities

This is a standalone Go module, not a root repository or production dependency.
Its checked-in `go.mod` and `go.sum` pin
`github.com/hashicorp/hcl/v2 v2.24.0` and
`github.com/zclconf/go-cty v1.16.3`, with exact indirect versions and checksums.
Published Terraform `v1.16.4` `go.mod` names HCL `v2.24.0`
(Git blob `14c79600e62bb4a47bb564f32295247707df3de1`).
The parser's own published module requires cty `v1.16.3`
(Git blob `6800390262667950e9d30aed433645b179b3526c`).
This does not reproduce Terraform's full dependency graph, build, evaluator, or
runtime semantics.

The HCL module checksums are:

```text
github.com/hashicorp/hcl/v2 v2.24.0 h1:2QJdZ454DSsYGoaE6QheQZjtKZSUs9Nh2izTWiwQxvE=
github.com/hashicorp/hcl/v2 v2.24.0/go.mod h1:oGoO1FIQYfn/AgyOhlg9qLC6/nOJPX3qGbkZpYAcqfM=
```

Go used the public module proxy and checksum database, with no private module
exceptions. The successful run verified all downloaded modules and required
`go mod tidy` to leave the checked-in manifest and checksum files unchanged.

| Tested file under `.github/offline-hcl-prototype` | Git blob |
| --- | --- |
| `analyzer.go` | `9a0a9989647130b5f200ebe2c3d339ecbcafcf59` |
| `analyzer_test.go` | `a2376fe15276c39a45dc705f54f7fb95cba698d0` |
| `traversal_test.go` | `d8e5c764c70c1c0d2dd481b7936d8093c9638515` |
| `go.mod` | `55d5890a9bf5287923c1319d9363f72400c5d6a3` |
| `go.sum` | `046687d7d66f447e1e737be3c1b6c147ab26e178` |

Manifest SHA-256:
`0bc2dfe457219fdfca771b78bd87faacae71b85514a71115a92aa481207164e2`.
Checksum-file SHA-256:
`b61c76061e594c0cfa1866e4e067aa579bf6bb61143b6724676200d03313c197`.

## Exact heads, CI, and restoration

New unmerged branch: `michael-rechani-hcl-syntax-prototype-20261107`.
Exact base on the observation branch:
`1c900fa9f8b9ba1103ddf22bc265d9b13a788b31`.
Edits used GitHub source APIs; no local project checkout or execution was used.

Initial head `4730856ea1093c124b28faae601f30b8aed751d6`,
[run 42421370791](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42421370791),
**failed before analyzer tests** because `go mod tidy` required canonical LF
line endings, removal of an unused manifest entry, and six additional checksum
lines for public dependency test packages. Module verification passed. Those
changes were checked in via the GitHub API; no stale-lock acceptance was added.

Original prototype tested head (before traversal correction):
`ac472033add028843ccb4e7cf82f27857325a422`,
[run 42421484518](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42421484518).
All actual-analyzer tests passed: 24 positive and 64 negative/adversarial examples,
plus encoding/format/size bounds, exact boundaries, redaction, full visitation,
key semantics and deterministic-count tests. Statement coverage was 94.0%.
`go vet` passed. A ten-second configured fuzz run with two workers completed
90946 executions without a failure (about eleven seconds elapsed, including
framework work). Fuzzing is not exhaustive proof.

CI used non-root `ubuntu-24.04` GitHub-hosted runners and Go `1.26.8`.
The only permission was `contents: read`; checkout selected the triggering exact
SHA with `persist-credentials: false`. Actions were pinned:

- Checkout: `3d3c42e5aac5ba805825da76410c181273ba90b1`.
- Setup Go: `924ae3a1cded613372ab5595356fb5720e22ba16`, exact toolchain version,
  dependency caching disabled.

Dependencies were resolved because the module manifests were new/changed.
For a source-only revision, the temporary workflow instead first ran the
selected compile validation with `GOPROXY=off`; restoration was permitted only
after that command reported missing public packages. No unconditional Ruff
installation, secrets, GitHub Environment, OIDC or artifact-download permission
was configured.

After validation, `.github/workflows/hcl-syntax-prototype.yml` was removed.
The final documentation/removal head is recorded in the session handoff.
Final corrected source and manifest blobs match the correction tested head.
Existing workflows and all parent files other than the isolated prototype
analyzer and this documentation remain byte-identical to the correction base.
The conservative HCL/JSON scanner and runtime/protected gates are unchanged.
No PR, merge or main change was made.

### Traversal-index correction

The previous tested head `ac472033add028843ccb4e7cf82f27857325a422` did
**not** enforce its documented indexing refusal: the pinned HCL parser folds
literal indexes into traversal steps rather than always producing `IndexExpr`.
Synthetic reproduction head `6451cfa55d4be9835791e17ea5440d03eaa0141d`,
[run 42421971889](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42421971889),
confirmed all 12 literal-index examples were incorrectly accepted.
Ordinary non-index traversals remained accepted.

The isolated correction checks every absolute and relative traversal's step
types. An absolute traversal must start with one nonempty `TraverseRoot`,
followed only by nonempty `TraverseAttr` steps; a relative traversal must be a
nonempty sequence of nonempty `TraverseAttr` steps. `TraverseIndex`,
`TraverseSplat`, nil, pointer forms, misplaced roots and any future or unknown
step kind are refused as `unsupported_expression`. No traversal is evaluated.

Fixed source head `b4bf5bff09c1058ff1a4e44c26865ec7ee7e5df9`,
[run 42422092698](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42422092698),
failed before the analyzer tests due to a misplaced brace in the newly added
synthetic test harness. The harness was corrected; the guard was unchanged.
Successful correction tested head `7e332165776687fd7c08477900fc581341f24a7e`,
[run 42422186512](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42422186512),
passed all tests and `go vet`; statement coverage was 94.6%. Parser-backed
tests explicitly verified actual `TraverseIndex` steps and refusal for 12
numeric, quoted/escaped string, legacy `.0`, chained and relative forms.
Six ordinary attribute-only/literal examples passed; nested refusal and 17
direct allowlist/visitor cases tested malformed, nil, and unsupported steps.
A 10-second configured fuzz run completed 125701 executions without failure.
Fuzzing and finite tests are not proof of completeness.

This correction used the previous temporary workflow with only `contents: read`;
its offline-first compile probe reported missing public packages before they
were restored, and `go mod verify` passed. No dependency manifest changed.
The temporary workflow was removed after CI; the final documentation/removal
head is recorded in the session handoff. No captured artifact or real closure
source was read.


## Uncovered meaning and protected boundaries

This predicate does not determine provider addresses or behavior, external or
computed values, variable/function semantics, module graphs, includes, other
files, JSON, runtime-root integrity, source authenticity, or dependency trust.
Ordinary traversals may refer to unknown values. Accepted static syntax is not
a certificate that a Terraform configuration is valid, safe, or bypass-free.
The strict unsupported-expression refusals mean this prototype is not evidence
that the real captured closure would pass.

No captured artifact or real closure source was retrieved for this follow-up.
No Terraform/provider, Azure/Foundry, private runner, protected credentials/data,
sudo, Docker, namespaces, other runner services or protected workflow changes
were used. The hosted runner is not a security sandbox and this work establishes
no host/token/process/filesystem/network isolation. It grants no authority for
diagnostic, plan, apply, deployment, a further artifact inspection or private
execution. Existing least-privilege boundaries remain unchanged.
