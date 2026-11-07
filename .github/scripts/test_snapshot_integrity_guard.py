import asyncio
import copy
import contextlib
import io
import os
import subprocess
import warnings
import unittest

import snapshot_integrity_guard as guard

EXPECTED = {'platform_state': 'https://fictional.invalid/cache/platform.tfstate',
            'input': 'https://fictional.invalid/cache/input.tfvars'}


def fixture():
    return {role: {'identity': identity, 'status': 200, 'body': b'fictional', 'headers': (
        ('ETag', '"fictional-version"'), ('Content-Length', '9'),
        ('Last-Modified', 'Sat, 07 Nov 2026 00:00:00 GMT'),
        ('x-ms-creation-time', 'Fri, 06 Nov 2026 00:00:00 GMT'),
        ('x-ms-version', '2023-11-03'), ('x-ms-blob-type', 'BlockBlob'),
        ('x-ms-lease-status', 'unlocked'), ('x-ms-lease-state', 'available'),
        ('x-ms-meta-owner', 'FICTIONAL_SECRET'))} for role, identity in EXPECTED.items()}


def change(pair, role, name, value):
    values = dict(pair[role]['headers'])
    values[name] = value
    pair[role]['headers'] = tuple(values.items())


class Tests(unittest.TestCase):
    def test_exact_and_volatile_only(self):
        before = fixture()
        after = fixture()
        self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.PASSED)
        change(after, 'input', 'Date', 'different-observation-time')
        change(after, 'input', 'x-ms-request-id', 'different-observation-id')
        self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.PASSED)

    def test_independent_mutations_and_restored_bytes_with_new_etag(self):
        for role in guard.ROLES:
            for kind in ('bytes', 'etag', 'metadata', 'modified', 'created', 'lease', 'state', 'duration', 'lock'):
                with self.subTest(role=role, kind=kind):
                    before, after = fixture(), fixture()
                    if kind == 'bytes':
                        after[role]['body'] = b'FICTIONAL'
                    else:
                        name, value = {'etag': ('ETag', '"new"'), 'metadata': ('x-ms-meta-owner', 'changed'),
                                       'modified': ('Last-Modified', 'Sun, 08 Nov 2026 00:00:00 GMT'),
                                       'created': ('x-ms-creation-time', 'Thu, 05 Nov 2026 00:00:00 GMT'),
                                       'lease': ('x-ms-lease-status', 'locked'), 'state': ('x-ms-lease-state', 'expired'),
                                       'duration': ('x-ms-lease-duration', 'fixed'),
                                       'lock': ('x-ms-meta-terraformlockid', 'FICTIONAL_SECRET')}[kind]
                        change(after, role, name, value)
                    self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)
            before, after = fixture(), fixture()
            after[role]['body'] = b'changed!!'
            after[role]['body'] = before[role]['body']
            change(after, role, 'ETag', '"new-after-restore"')
            self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)

    def test_full_schema_missing_extra_ambiguous_and_identity(self):
        for mutation in ('missing-role', 'extra-role', 'identity', 'status-bool', 'empty', 'body-type',
                         'extra-field', 'missing-header', 'duplicate', 'unknown', 'extra-meta', 'missing-meta',
                         'header-type', 'header-value', 'partial', 'api', 'version', 'range', 'alias'):
            with self.subTest(mutation=mutation):
                before, after = fixture(), fixture()
                snap = after['input']
                if mutation == 'missing-role': del after['input']
                elif mutation == 'extra-role': after['extra'] = snap
                elif mutation == 'identity': snap['identity'] = EXPECTED['platform_state']
                elif mutation == 'status-bool': snap['status'] = True
                elif mutation == 'empty': snap['body'] = b''
                elif mutation == 'body-type': snap['body'] = bytearray(b'fictional')
                elif mutation == 'extra-field': snap['unknown'] = 'FICTIONAL_SECRET'
                elif mutation == 'missing-header': snap['headers'] = snap['headers'][1:]
                elif mutation == 'duplicate': snap['headers'] += (('etag', '"fictional-version"'),)
                elif mutation == 'unknown': change(after, 'input', 'x-ms-unreviewed', 'value')
                elif mutation == 'extra-meta': change(after, 'input', 'x-ms-meta-extra', 'value')
                elif mutation == 'missing-meta': snap['headers'] = snap['headers'][:-1]
                elif mutation == 'header-type': snap['headers'] = dict(snap['headers'])
                elif mutation == 'header-value': change(after, 'input', 'ETag', 'FICTIONAL_SECRET\n')
                elif mutation == 'partial': snap['status'] = 206
                elif mutation == 'api': change(after, 'input', 'x-ms-version', 'other')
                elif mutation == 'version': change(after, 'input', 'x-ms-version-id', 'unreviewed')
                elif mutation == 'range': change(after, 'input', 'Content-Range', 'bytes 0-8/9')
                else: snap['identity'] += '?versionid=old'
                self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)

    def test_all_failure_paths_recheck_both_roles_and_redact(self):
        for phase in ('success', 'error', 'timeout', 'cancel', 'async-cancel', 'before-state', 'before-input', 'after-state', 'after-input'):
            with self.subTest(phase=phase):
                calls = []
                stdout, stderr = io.StringIO(), io.StringIO()
                def read(role):
                    calls.append(role)
                    print('FICTIONAL_SECRET')
                    stage = 'before' if len(calls) <= 2 else 'after'
                    if phase == stage + ('-state' if role == 'platform_state' else '-input'):
                        raise TimeoutError('FICTIONAL_SECRET')
                    return fixture()[role]
                def diagnostic():
                    print('FICTIONAL_SECRET')
                    if phase == 'error': raise RuntimeError('FICTIONAL_SECRET')
                    if phase == 'timeout': raise TimeoutError('FICTIONAL_SECRET')
                    if phase == 'cancel': raise KeyboardInterrupt('FICTIONAL_SECRET')
                    if phase == 'async-cancel': raise asyncio.CancelledError('FICTIONAL_SECRET')
                    return guard.DIAGNOSTIC_SUCCESS
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    outcome = guard.guarded_diagnostic(EXPECTED, read, diagnostic)
                self.assertEqual(calls, ['platform_state', 'input'] * 2)
                expected = guard.PASSED if phase == 'success' else (
                    guard.FAILED if phase in ('error', 'timeout', 'cancel', 'async-cancel') else guard.UNVERIFIED)
                self.assertEqual(outcome, expected)
                self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')

    def test_instability_precedes_diagnostic_error_and_second_read_failure(self):
        for role in guard.ROLES:
            for failed in (False, True):
                calls = []
                def read(name):
                    calls.append(name)
                    pair = fixture()
                    if len(calls) > 2:
                        change(pair, role, 'ETag', '"changed"')
                    return pair[name]
                def diagnostic():
                    if failed: raise RuntimeError('FICTIONAL_SECRET')
                self.assertEqual(guard.guarded_diagnostic(EXPECTED, read, diagnostic), guard.UNVERIFIED)
                self.assertEqual(calls, ['platform_state', 'input'] * 2)

    def test_callback_cannot_rewrite_baseline(self):
        pair = fixture()
        def diagnostic():
            change(pair, 'input', 'ETag', '"rewritten"')
        self.assertEqual(guard.guarded_diagnostic(EXPECTED, lambda role: pair[role], diagnostic), guard.UNVERIFIED)

    def test_identical_endpoints_cannot_detect_transient_lock(self):
        pair = fixture()
        def diagnostic():
            change(pair, 'input', 'x-ms-lease-status', 'locked')
            change(pair, 'input', 'x-ms-lease-status', 'unlocked')
            return guard.DIAGNOSTIC_SUCCESS
        self.assertEqual(guard.guarded_diagnostic(EXPECTED, lambda role: pair[role], diagnostic), guard.PASSED)


    def test_invalid_before_skips_operation_and_every_read_still_attempted(self):
        for case in ('identity', 'schema', 'locked', 'both-read-errors'):
            with self.subTest(case=case):
                calls = []
                def read(role):
                    calls.append(role)
                    if case == 'both-read-errors': raise RuntimeError('FICTIONAL_SECRET')
                    pair = fixture()
                    if len(calls) <= 2:
                        if case == 'identity': pair[role]['identity'] += '?secret=FICTIONAL_SECRET'
                        elif case == 'schema': pair[role]['unknown'] = None
                        else: change(pair, role, 'x-ms-lease-status', 'locked')
                    return pair[role]
                def forbidden():
                    self.fail('Invalid baseline must not execute diagnostic')
                self.assertEqual(guard.guarded_diagnostic(EXPECTED, read, forbidden), guard.UNVERIFIED)
                self.assertEqual(calls, ['platform_state', 'input'] * 2)

    def test_expected_mutation_cannot_rebind_identity(self):
        expected = dict(EXPECTED)
        pair = fixture()
        def diagnostic():
            expected['input'] = 'https://fictional.invalid/cache/replacement'
            pair['input']['identity'] = expected['input']
        self.assertEqual(guard.guarded_diagnostic(expected, lambda role: pair[role], diagnostic), guard.UNVERIFIED)

    def test_invalid_expected_still_checks_both_boundaries(self):
        for expected in (None, {}, {'input': 'FICTIONAL_SECRET'},
                         {'platform_state': EXPECTED['input'], 'input': EXPECTED['input']}):
            calls = []
            def read(role):
                calls.append(role)
                return fixture()[role]
            self.assertEqual(guard.guarded_diagnostic(expected, read, lambda: self.fail('must skip')), guard.UNVERIFIED)
            self.assertEqual(calls, ['platform_state', 'input'] * 2)

    def test_execution_is_non_root_without_credential_environment(self):
        self.assertNotEqual(os.geteuid(), 0)
        self.assertFalse(any(name.startswith(('AZURE_', 'ARM_', 'ACTIONS_ID_TOKEN_'))
                             or name in ('GH_TOKEN', 'GITHUB_TOKEN') for name in os.environ))

    def test_optional_version_presence_and_bytes_are_exact(self):
        before, after = fixture(), fixture()
        change(before, 'input', 'x-ms-version-id', 'fictional-version-1')
        change(after, 'input', 'x-ms-version-id', 'fictional-version-1')
        self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.PASSED)
        change(after, 'input', 'x-ms-version-id', 'fictional-version-2')
        self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)
        after = fixture()
        self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)
        change(after, 'input', 'x-ms-version-id', '')
        self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)

    def test_bounds_and_invalid_dates_and_identity_fail_closed(self):
        for mutation in ('many-headers', 'huge-value', 'bad-date', 'bad-weekday', 'missing-version',
                         'list-pair', 'body-length', 'lease-breaking', 'weak-etag'):
            before, after = fixture(), fixture()
            snap = after['input']
            if mutation == 'many-headers': snap['headers'] *= 129
            elif mutation == 'huge-value': change(after, 'input', 'x-ms-meta-owner', 'X' * 8193)
            elif mutation == 'bad-date': change(after, 'input', 'Last-Modified', 'Sat, 99 Nov 2026 00:00:00 GMT')
            elif mutation == 'bad-weekday': change(after, 'input', 'Last-Modified', 'Sun, 07 Nov 2026 00:00:00 GMT')
            elif mutation == 'missing-version': snap['headers'] = tuple(pair for pair in snap['headers'] if pair[0] != 'x-ms-version')
            elif mutation == 'list-pair': snap['headers'] += (['x-ms-meta-other', 'value'],)
            elif mutation == 'body-length': change(after, 'input', 'Content-Length', '09')
            elif mutation == 'lease-breaking': change(after, 'input', 'x-ms-lease-state', 'breaking')
            else: change(after, 'input', 'ETag', 'W/"weak"')
            self.assertEqual(guard.compare_snapshots(EXPECTED, before, after), guard.UNVERIFIED)
        for identity in ('https://user:FICTIONAL_SECRET@fictional.invalid/cache/blob',
                         'http://fictional.invalid/cache/blob', 'https://fictional.invalid/cache/../blob',
                         'https://fictional.invalid/cache/blob#secret', 'https://fictional.invalid/cache/%62lob'):
            expected = dict(EXPECTED, input=identity)
            self.assertEqual(guard.compare_snapshots(expected, fixture(), fixture()), guard.UNVERIFIED)

    def test_identical_restored_bytes_and_all_headers_are_not_history(self):
        pair = fixture()
        def diagnostic():
            pair['input']['body'] = b'transient'
            pair['input']['body'] = b'fictional'
            return guard.DIAGNOSTIC_SUCCESS
        self.assertEqual(guard.guarded_diagnostic(EXPECTED, lambda role: pair[role], diagnostic), guard.PASSED)

    def test_only_exact_synchronous_success_token_passes(self):
        class EqualToAnything:
            def __eq__(self, other):
                raise AssertionError('must use identity, not equality')
        values = (None, False, True, 0, 1, 2, '', 'success', object(), EqualToAnything(),
                  subprocess.CompletedProcess(['fictional'], 1),
                  subprocess.CompletedProcess(['fictional'], 0))
        for value in (guard.DIAGNOSTIC_SUCCESS,) + values:
            with self.subTest(value_type=type(value).__name__):
                calls = []
                def read(role):
                    calls.append(role)
                    return fixture()[role]
                outcome = guard.guarded_diagnostic(EXPECTED, read, lambda: value)
                self.assertEqual(outcome, guard.PASSED if value is guard.DIAGNOSTIC_SUCCESS else guard.FAILED)
                self.assertEqual(calls, ['platform_state', 'input'] * 2)

    def test_unsupervised_awaitables_fail_without_execution_or_disclosure(self):
        touched = []
        class FictionalAwaitable:
            def __await__(self):
                touched.append('executed')
                yield
                return guard.DIAGNOSTIC_SUCCESS
        async def unexecuted():
            touched.append('executed')
            return guard.DIAGNOSTIC_SUCCESS
        for factory in (FictionalAwaitable, unexecuted):
            with self.subTest(factory=factory.__name__):
                calls = []
                def read(role):
                    calls.append(role)
                    return fixture()[role]
                stdout, stderr = io.StringIO(), io.StringIO()
                with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    warnings.simplefilter('always')
                    result = guard.guarded_diagnostic(EXPECTED, read, factory)
                self.assertEqual(result, guard.FAILED)
                self.assertEqual(calls, ['platform_state', 'input'] * 2)
                self.assertEqual(touched, [])
                self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')
                self.assertFalse(any(issubclass(w.category, RuntimeWarning) for w in caught))

    def test_callback_results_and_exceptions_never_override_unstable_snapshots(self):
        class CustomAwaitable:
            def __await__(self):
                raise AssertionError('must not execute awaitable')
                yield
        for outcome in ('success', 'false', 'integer', 'awaitable', 'raise', 'cancel'):
            for invalid in ('state-change', 'input-invalid', 'input-read-failure'):
                with self.subTest(outcome=outcome, invalid=invalid):
                    calls = []
                    def read(role):
                        calls.append(role)
                        snap = fixture()
                        if len(calls) > 2 and role == 'platform_state' and invalid == 'state-change':
                            change(snap, role, 'ETag', '"different"')
                        if len(calls) > 2 and role == 'input' and invalid == 'input-invalid':
                            change(snap, role, 'x-ms-lease-status', 'locked')
                        if len(calls) > 2 and role == 'input' and invalid == 'input-read-failure':
                            raise TimeoutError('FICTIONAL_SECRET')
                        return snap[role]
                    def diagnostic():
                        if outcome == 'raise': raise RuntimeError('FICTIONAL_SECRET')
                        if outcome == 'cancel': raise KeyboardInterrupt('FICTIONAL_SECRET')
                        return {'success': guard.DIAGNOSTIC_SUCCESS, 'false': False,
                                'integer': 1, 'awaitable': CustomAwaitable()}[outcome]
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        result = guard.guarded_diagnostic(EXPECTED, read, diagnostic)
                    self.assertEqual(result, guard.UNVERIFIED)
                    self.assertEqual(calls, ['platform_state', 'input'] * 2)
                    self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')

    def test_invalid_baseline_cannot_be_overridden_by_success_token(self):
        calls, invoked = [], []
        def read(role):
            calls.append(role)
            snap = fixture()
            if len(calls) <= 2 and role == 'input':
                change(snap, role, 'x-ms-lease-status', 'locked')
            return snap[role]
        def diagnostic():
            invoked.append(True)
            return guard.DIAGNOSTIC_SUCCESS
        self.assertEqual(guard.guarded_diagnostic(EXPECTED, read, diagnostic), guard.UNVERIFIED)
        self.assertEqual(calls, ['platform_state', 'input'] * 2)
        self.assertEqual(invoked, [])

    def test_suspended_coroutine_and_unresolved_future_are_not_awaited_or_cancelled(self):
        events = []
        class Pause:
            def __await__(self):
                events.append('began')
                yield 'paused'
                events.append('resumed')
        async def unfinished():
            await Pause()
            return guard.DIAGNOSTIC_SUCCESS
        coroutine = unfinished()
        self.assertEqual(coroutine.send(None), 'paused')
        loop = asyncio.new_event_loop()
        try:
            future = loop.create_future()
            for result in (coroutine, future):
                calls = []
                def read(role):
                    calls.append(role)
                    return fixture()[role]
                self.assertEqual(guard.guarded_diagnostic(EXPECTED, read, lambda: result), guard.FAILED)
                self.assertEqual(calls, ['platform_state', 'input'] * 2)
            self.assertEqual(events, ['began'])
            self.assertFalse(future.done())
        finally:
            coroutine.close()
            future.cancel()
            loop.close()

if __name__ == '__main__':
    unittest.main()
