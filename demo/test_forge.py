import base64
import json
import unittest

from forge import forge_unsigned_jwt


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


class ForgeUnsignedJwtTest(unittest.TestCase):
    def test_token_is_unsigned_with_none_alg_claiming_the_email(self):
        email = "jwtn3d@juice-sh.op"

        token = forge_unsigned_jwt(email)

        parts = token.split(".")
        self.assertEqual(len(parts), 3, "a JWT has three dot-separated segments")
        self.assertEqual(parts[2], "", "an unsigned token carries an empty signature")

        header = json.loads(_b64url_decode(parts[0]))
        self.assertEqual(header, {"alg": "none", "typ": "JWT"})

        payload = json.loads(_b64url_decode(parts[1]))
        self.assertEqual(payload["data"]["email"], email)


if __name__ == "__main__":
    unittest.main()
