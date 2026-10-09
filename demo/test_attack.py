import unittest

from attack import _build_request, verdict_for


class BuildRequestTest(unittest.TestCase):
    def test_sets_a_browser_user_agent_so_cloudflare_allows_it(self):
        req = _build_request("GET", "https://juiceshop.rootlane.xyz/api/Products")

        user_agent = req.get_header("User-agent", "")
        self.assertIn("Mozilla", user_agent)
        self.assertNotIn("urllib", user_agent.lower())

    def test_keeps_an_explicit_user_agent(self):
        req = _build_request(
            "GET", "https://example.test", headers={"User-Agent": "custom-agent"}
        )

        self.assertEqual(req.get_header("User-agent"), "custom-agent")


class VerdictForTest(unittest.TestCase):
    def test_accepted_response_reads_as_vulnerable(self):
        label, note = verdict_for(200)

        self.assertEqual(label, "VULNERABLE")
        self.assertIn("ACCEPTED", note)

    def test_rejected_response_reads_as_protected(self):
        label, note = verdict_for(401)

        self.assertEqual(label, "PROTECTED")
        self.assertIn("REJECTED", note)


if __name__ == "__main__":
    unittest.main()
