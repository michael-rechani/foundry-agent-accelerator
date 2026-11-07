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
6. Stayed within the 256-token budget for the specified structural operator
   kinds; the budget is checked after lexing and before parsing.

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

Inputs must be nonempty and at most 65536 bytes. The pinned lexer processes the
input before the analyzer checks a maximum of 8192 tokens, lexical nesting of
32, and 256 specified structural operator tokens. AST depth 128 and node count
16384 are refusal/reporting thresholds only: `hclsyntax.Walk` does not prune
after either is reached. See the measured cases and their limits below. None of
these thresholds proves a hard parser/walker stack, memory, or time bound.

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
| `analyzer.go` | `0da59505b3861caf08446952fb83f315d20653d1` |
| `analyzer_test.go` | `a2376fe15276c39a45dc705f54f7fb95cba698d0` |
| `traversal_test.go` | `d8e5c764c70c1c0d2dd481b7936d8093c9638515` |
| `ast_bounds_test.go` | `648d3c5a727980352c6d5253598f85815f863f7f` |
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
Final source and manifest blobs match the later AST-bounds tested head below.
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


### AST refusal thresholds and operator budget

The prior implementation's `MaxASTDepth=128` and `MaxNodes=16384` are
**refusal/reporting thresholds, not hard walker resource bounds**.
`hclsyntax.Walk` unconditionally visits children after `Enter`; the analyzer's
`bounds_refused` category does not prune traversal or limit stack usage.
The reported `Nodes` value saturates at 16384; it is not the number actually
visited once that threshold is crossed.

A targeted, narrower early guard now counts the pinned lexer's structural
operator tokens across the whole file. More than 256 recognized tokens returns
`bounds_refused` **after lexing and before parsing**. The counted token kinds
are `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`,
`!`, and `?`; the budget is global, not per expression. This only adds a
refusal path, never an acceptance path. Operator-looking bytes inside comments,
plain strings and heredocs remain lexer text rather than structural tokens;
synthetic tests cover long inert examples of all listed kinds and ordinary
assignments/hyphenated identifiers.

The guard limits this explicit set of lexer tokens reaching the parser. It is
not a general bound on parser work, AST depth/node count, recursion, memory,
execution time, or unrecognized constructs. The lexer itself has already
processed the bounded byte input before token/operator checks run. Inputs at or
below the operator budget can still exceed the AST refusal thresholds, and
other inputs can produce different shapes. No hard stack/time bound or sandbox
is established.

Parser-backed synthetic measurements used HCL `v2.24.0` and the same
`hclsyntax.Walk`:

| Chain | Bytes | Tokens | Lexical depth | Measured AST depth | Full walker nodes | Analyzer outcome |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 121 terms | 260 | 247 | 1 | 127 | 249 | `unsupported_expression` |
| 122 terms | 262 | 249 | 1 | 128 | 251 | `unsupported_expression` |
| 123 terms | 264 | 251 | 1 | 129 | 253 | `bounds_refused,unsupported_expression` |
| 257 terms, 256 operators | 532 | 519 | 1 | 263 | 521 | Both categories; full walker |
| 258 terms, 257 operators | 534 | 521 | 1 | 264 | 523 | `bounds_refused`; analyzer AST nodes 0 |
| 4093 terms | 8205 | 8192 | 1 | 4099 | 8193 | `bounds_refused`; analyzer AST nodes 0 |

For the last two rows the full walker was run separately **by the test** on
the parser-generated synthetic AST to measure the shape; the guarded analyzer
returned before parsing it. The 4093-term sample is the longest tested
same-operator chain at the 8192-token input limit, not a maximum over all
possible inputs. At the pre-guard baseline it was actually parsed and fully
walked by the analyzer despite its depth refusal.

A separate **fabricated AST**, not an AST parsed from an admitted source,
contained 16455 visited nodes. The analyzer reported the capped count 16384
and still visited a provider block at the end. This demonstrates that the node
threshold does not prune; it does not prove a valid in-budget source can reach
that node count.

The baseline measurement head was
`a4c4bc96bfb91fb7bdc26482af512358f1c258cf`,
[run 42422911250](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42422911250).
The operator guard first passed at
`9d68f2c185fafc018a2a7356e7ccbdbb646f7f5e`,
[run 42423073082](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42423073082).
The strengthened final tested head was
`263758b332b2f3cc9d5f516d2f92a20b524d2021`,
[run 42423282526](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42423282526).
Deterministic tests and `go vet` passed in both attempts, with 96.4% statement
coverage. Fuzz attempt 1 failed with `context deadline exceeded` and reported
no failing input; its cause is unknown. A same-head attempt 2 passed after
166888 executions in a 10-second-configured, two-worker fuzz run. The retry
does not explain the earlier failure or establish a hard time bound.

The unchanged temporary workflow used non-root GitHub-hosted CI, pinned actions,
and `contents: read` only. Its offline-first dependency probe failed for missing
public packages before restoration; manifests did not change and module
verification passed. After testing, the temporary workflow was removed and
existing workflows, the conservative scanner, traversal-index guard, and
runtime/protected gates were preserved.


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

### Synthetic fuzz-deadline investigation

The original [run 42423282526](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42423282526), attempt 1,
still stands: its fuzz command failed with `context deadline exceeded`, after
90303 reported executions, without a reported reproducer. Its cause is unknown;
the passing attempt 2 did not establish reliability.

The investigation started from exact head
`0b45cc851bd3b8f2391b7d148dc0e1f3d5366c5f`, made no analyzer or dependency
changes, and used exactly two additional synthetic-only hosted runs:

| Run | Tested commit | Synthetic tests and vet | Fuzz results |
| --- | --- | --- | --- |
| [42424442927](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42424442927) | `d7e70a48775e4ec4d9e112a6668a1fcb9db04174` | Passed; 96.4% statement coverage | Four original `FuzzAnalyze` and four no-op-control invocations passed |
| [42424684586](https://github.com/michael-rechani/foundry-agent-accelerator/actions/runs/42424684586) | `bf86acc3af5047406dbaff65133514a483ac63af` | Passed; 96.4% statement coverage | Six actual Go `PASS`/`ok` pairs observed with coordinator debug; wrapper-status limitation below |

Per-command log evidence distinguishes the Go results from the temporary
wrapper's behavior. Run 42424442927 contains eight actual Go `PASS`/`ok` pairs;
run 42424684586 contains six, with no observed Go failure lines. However, the
second run piped `go test` into `awk` under GitHub's `/usr/bin/bash -e {0}`
without `pipefail`. Its pipeline status therefore reflected `awk`, not the Go
command, and the wrapper's success status alone could have masked a failed Go
command. The reported per-command successes are supported by the actual Go log
lines, not by wrapper success markers or the job conclusion alone. This is an
identified harness limitation; it does not explain the original fuzz deadline.
No additional CI was run to correct or validate the retired wrapper, and the
temporary workflow remains absent.

Each invocation used Go 1.26.8, a 10-second fuzz duration and two workers.
The second run set `GODEBUG=fuzzdebug=1` and printed the last at most 30
coordinator debug lines per invocation, plus the total debug-line count; debug
instrumentation can change timing. The fuzz cache was reused within each run,
so rounds are not independent. The no-op control uses the same fuzz machinery,
but does not perform equivalent analyzer or parser work.

In the first run, all analyzer rounds passed, but rounds 2-4 reported no new
executions between the 3-second and 11-second progress lines. The second run's
analyzer rounds also had intervals reporting zero new executions. These are
progress reports, not proof that no processing occurred. The no-op control
continued to report progress but its rate varied markedly. Bounded debug output
included coverage-minimization queue events and coordinator stop events, but
did not identify the in-flight inputs, worker stacks, or a cause for the
original failure. Neither timeouts nor a failing input reproduced; no claim
about the original cause, a Go defect, analyzer reliability, or a time bound
follows.

The new parser-backed cases exercise decimal mantissas up to the exact
65536-byte input limit, a large decimal exponent, a long normalized Unicode
string, a 4000-attribute traversal and a 1200-key object. They call the actual
analyzer twice and require deterministic accepted results. Parsing of long
numeric literals is a plausible workload to examine because HCL passes them
through cty to Go's `math/big`; there is no evidence that such a literal was
in the original failed run. Across these cases in the second run, the largest
observed individual analyzer call was about 13.42 ms for the 65536-byte number;
these measurements are samples on one hosted runner, not worst-case bounds.

The added `fuzz_deadline_stress_test.go` has Git blob
`cc61fd336d8ce3e0f81a7b159eb8b0ace1945a3d`; the analyzer, original fuzz tests,
traversal tests, AST-bounds tests and module blobs remain as listed above. Both
runs used non-root GitHub-hosted Ubuntu with pinned actions, `contents: read`
only, no persisted checkout credentials, secrets, Environment, OIDC, private
runner or artifact access. The offline compile probe first failed for missing
public packages; only then were modules downloaded and verified. The temporary
workflow was removed after testing; existing workflows and runtime/protected
gates remain unchanged. No PR or merge was made.
