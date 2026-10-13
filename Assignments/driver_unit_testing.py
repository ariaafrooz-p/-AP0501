import unittest
from decimal import Decimal


class TestDriver(unittest.TestCase):
    def setUp(self):
        Driver.total_drivers = 0
        Driver.company_credit = Decimal('0')

    def test_delivery_sets_position_to_destination(self):
        driver = Driver('Ali123', (1, 2))
        driver.assign_order(Decimal('100'), (5, 6))

        driver.deliver()

        self.assertEqual(driver.position, (5, 6))
        self.assertEqual(driver.status, 'FREE')

    def test_company_credit_is_20_percent_of_order(self):
        driver = Driver('Ali123', (1, 2))
        driver.assign_order(Decimal('100'), (5, 6))

        driver.deliver()

        self.assertEqual(driver.credit, Decimal('80'))
        self.assertEqual(Driver.company_credit, Decimal('20'))

    def test_deliver_requires_active_order(self):
        driver = Driver('Ali123', (1, 2))

        with self.assertRaises(RuntimeError):
            driver.deliver()


# In the course notebook, use the existing run_tests function:
run_tests(TestDriver)

# Or, in an independent .py file, replace the line above with:
# if __name__ == '__main__':
#     unittest.main()
