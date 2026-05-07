import unittest

from greeter import greet


class GreeterTests(unittest.TestCase):
    def test_greets_ada(self) -> None:
        self.assertEqual(greet("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
