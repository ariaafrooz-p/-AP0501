import unittest

class TestDriver(unittest.TestCase):
    def setUp(self):
        self.driver = Driver()

    def test_driver_initialization(self):
        self.assertIsNotNone(self.driver)

    def test_driver_movement(self):
        initial_position = self.driver.position
        self.driver.move_forward()
        self.assertEqual(self.driver.position, initial_position + 1)