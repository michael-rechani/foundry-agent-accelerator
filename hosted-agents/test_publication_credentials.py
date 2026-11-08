import os
import unittest
from pathlib import Path
from unittest.mock import patch

import deployment


class PublicationCredentialTests(unittest.TestCase):
    CLIENT_ID = "12345678-1234-1234-1234-123456789abc"

    def setUp(self):
        self.profile = deployment.AgentProfile(Path("."), "fictional-agent", "fictional", "fictional", "")
        self.environment = self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.default = self.enterContext(patch("azure.identity.DefaultAzureCredential"))
        self.managed = self.enterContext(patch("azure.identity.ManagedIdentityCredential"))
        self.workload = self.enterContext(patch("azure.identity.WorkloadIdentityCredential"))
        self.base = ["--endpoint", "https://fictional.invalid", "--model", "fictional-router"]

    def test_missing_ambiguous_malformed_or_changed_selections_rejected(self):
        invalid = (
            (None, self.CLIENT_ID, None, self.CLIENT_ID),
            ("dev", self.CLIENT_ID, "dev", self.CLIENT_ID),
            ("EnvironmentCredential", self.CLIENT_ID, "EnvironmentCredential", self.CLIENT_ID),
            ("ManagedIdentityCredential,WorkloadIdentityCredential", self.CLIENT_ID, None, self.CLIENT_ID),
            ("ManagedIdentityCredential", None, "ManagedIdentityCredential", None),
            ("ManagedIdentityCredential", "bad", "ManagedIdentityCredential", "bad"),
            ("WorkloadIdentityCredential", self.CLIENT_ID, "ManagedIdentityCredential", self.CLIENT_ID),
            ("ManagedIdentityCredential", self.CLIENT_ID, "ManagedIdentityCredential",
             "abcdefab-1234-1234-1234-123456789abc"),
        )
        for mode, client, env_mode, env_client in invalid:
            with self.subTest(mode=mode, client=client, env_mode=env_mode), patch.dict(os.environ, {}, clear=True):
                if env_mode is not None:
                    os.environ["AZURE_TOKEN_CREDENTIALS"] = env_mode
                if env_client is not None:
                    os.environ["AZURE_CLIENT_ID"] = env_client
                with self.assertRaises(ValueError):
                    deployment.publication_credential(mode, client)
        self.default.assert_not_called()
        self.managed.assert_not_called()
        self.workload.assert_not_called()

    def test_cli_rejects_missing_or_inconsistent_opt_in_pair(self):
        os.environ["AZURE_TOKEN_CREDENTIALS"] = "ManagedIdentityCredential"
        os.environ["AZURE_CLIENT_ID"] = self.CLIENT_ID
        for extra in (
            ["--credential-mode", "ManagedIdentityCredential"],
            ["--credential-client-id", self.CLIENT_ID],
            ["--credential-mode", "EnvironmentCredential", "--credential-client-id", self.CLIENT_ID],
            ["--credential-mode", "ManagedIdentityCredential", "--credential-client-id", "invalid"],
            ["--credential-mode", "WorkloadIdentityCredential", "--credential-client-id", self.CLIENT_ID],
        ):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as result:
                deployment.parse_args(self.profile, self.base + extra)
            self.assertEqual(result.exception.code, 2)
        self.default.assert_not_called()
        self.managed.assert_not_called()
        self.workload.assert_not_called()

    def test_each_selected_credential_has_only_explicit_class_and_client(self):
        for mode, selected, other in (
            ("ManagedIdentityCredential", self.managed, self.workload),
            ("WorkloadIdentityCredential", self.workload, self.managed),
        ):
            with self.subTest(mode=mode), patch.dict(os.environ, {
                "AZURE_TOKEN_CREDENTIALS": mode, "AZURE_CLIENT_ID": self.CLIENT_ID,
            }, clear=True):
                self.managed.reset_mock()
                self.workload.reset_mock()
                args = deployment.parse_args(self.profile, self.base + [
                    "--credential-mode", mode, "--credential-client-id", self.CLIENT_ID])
                self.assertIs(deployment.publication_credential(args.credential_mode, args.credential_client_id),
                              selected.return_value)
                selected.assert_called_once_with(client_id=self.CLIENT_ID)
                other.assert_not_called()
                self.default.assert_not_called()

    def test_no_opt_in_preserves_developer_default_credential(self):
        args = deployment.parse_args(self.profile, self.base)
        self.assertIs(deployment.publication_credential(args.credential_mode, args.credential_client_id),
                      self.default.return_value)
        self.default.assert_called_once_with()
        self.managed.assert_not_called()
        self.workload.assert_not_called()
