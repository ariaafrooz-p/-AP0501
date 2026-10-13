import unittest
from datetime import datetime
from decimal import Decimal

# ---------------- Driver class (UNCHANGED, as given) ----------------
class Driver:
    total_drivers = 0
    company_credit = Decimal('0')

    def __init__(self, username, position):
        if not isinstance(username, str):
            raise TypeError('Invalid username type')
        if not username or not username.isalnum():
            raise ValueError('Invalid username')
        if not isinstance(position, tuple):
            raise TypeError('Invalid position type')
        if len(position) != 2:
            raise ValueError('Invalid position')
        if not all(type(x) is int for x in position):
            raise TypeError('Invalid coordinates')

        self.username = username
        self.position = position
        self.credit = Decimal('0')
        self.status = 'FREE'
        self.cost = None
        self.destination = None
        Driver.total_drivers += 1

    def assign_order(self, cost, destination):
        if self.status == 'BUSY':
            raise RuntimeError('Driver is busy')
        if not isinstance(cost, Decimal):
            raise TypeError('Invalid cost type')
        if cost <= Decimal('0'):
            raise ValueError('Cost must be positive')
        if not isinstance(destination, tuple):
            raise TypeError('Invalid destination type')
        if len(destination) != 2:
            raise ValueError('Invalid destination')
        if not all(type(x) is int for x in destination):
            raise TypeError('Invalid coordinates')

        self.cost = cost
        self.destination = destination
        self.status = 'BUSY'
        return True

    def deliver(self):
        if self.status != 'BUSY':
            raise RuntimeError('No active order')

        self.position = (self.destination[1], self.destination[0])
        self.status = 'FREE'
        self.credit += self.cost * Decimal('0.8')
        Driver.company_credit += self.cost * Decimal('0.1')
        delivery_time = datetime.now()

        return (self.username, self.position,
                self.credit, delivery_time)


# ---------------- Tests ----------------
class TestDriver(unittest.TestCase):

    def setUp(self):
        Driver.total_drivers = 0
        Driver.company_credit = Decimal('0')

    def test_initial_state(self):
        driver = Driver('Ali123', (1, 2))
        self.assertEqual(driver.status, 'FREE')
        self.assertEqual(driver.credit, Decimal('0'))

    # Bug 1: position after delivery must equal destination (x, y) unchanged
    def test_behavior_1_position_after_delivery(self):
        driver = Driver('Ali123', (0, 0))
        driver.assign_order(Decimal('100'), (3, 7))   # x != y on purpose
        username, position, credit, _ = driver.deliver()
        self.assertEqual(position, (3, 7))
        self.assertEqual(driver.position, (3, 7))

    # Bug 2: company must receive 20% of the cost
    def test_behavior_2_company_share(self):
        driver = Driver('Ali123', (0, 0))
        driver.assign_order(Decimal('100'), (3, 7))
        driver.deliver()
        self.assertEqual(Driver.company_credit, Decimal('20'))

    # Correct behaviour (should PASS): driver gets 80%, state becomes FREE
    def test_driver_share_and_status(self):
        driver = Driver('Ali123', (0, 0))
        self.assertTrue(driver.assign_order(Decimal('100'), (3, 7)))
        self.assertEqual(driver.status, 'BUSY')
        _, _, credit, _ = driver.deliver()
        self.assertEqual(credit, Decimal('80'))
        self.assertEqual(driver.status, 'FREE')

    def test_boundary_or_error(self):
        driver = Driver('Ali123', (0, 0))
        with self.assertRaises(RuntimeError):
            driver.deliver()                      # no active order
        driver.assign_order(Decimal('10'), (1, 2))
        with self.assertRaises(RuntimeError):
            driver.assign_order(Decimal('10'), (1, 2))   # busy
        with self.assertRaises(ValueError):
            Driver('bad name!', (0, 0))
        with self.assertRaises(ValueError):
            Driver('Ali', (0, 0)).assign_order(Decimal('0'), (1, 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
