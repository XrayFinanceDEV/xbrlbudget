"""
Base Calculator Framework
Provides common utilities for financial calculations
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Union, Optional
from config import DECIMAL_PLACES


class CalculationError(Exception):
    """Raised when a calculation cannot be performed"""
    pass


class BaseCalculator:
    """
    Base class for all financial calculators
    Provides Excel-like utility functions
    """

    @staticmethod
    def safe_divide(numerator: Union[Decimal, float, int],
                   denominator: Union[Decimal, float, int],
                   default: Union[Decimal, float, int] = 0) -> Decimal:
        """
        Safe division with zero-division protection (IFERROR equivalent)

        Args:
            numerator: The dividend
            denominator: The divisor
            default: Value to return if division by zero (default: 0)

        Returns:
            Result of division or default value
        """
        try:
            num = Decimal(str(numerator))
            den = Decimal(str(denominator))

            if den == 0:
                return Decimal(str(default))

            return num / den
        except (ValueError, TypeError, ArithmeticError):
            return Decimal(str(default))

    @staticmethod
    def round_decimal(value: Union[Decimal, float, int],
                     decimal_places: int = 2) -> Decimal:
        """
        Round a value to specified decimal places

        Args:
            value: Value to round
            decimal_places: Number of decimal places (default: 2)

        Returns:
            Rounded Decimal value
        """
        try:
            val = Decimal(str(value))
            quantizer = Decimal('0.1') ** decimal_places
            return val.quantize(quantizer, rounding=ROUND_HALF_UP)
        except (ValueError, TypeError):
            return Decimal('0')

    @staticmethod
    def to_percentage(value: Union[Decimal, float, int],
                     decimal_places: int = 2) -> Decimal:
        """
        Convert a ratio to percentage and round

        Args:
            value: Ratio value (e.g., 0.15 for 15%)
            decimal_places: Decimal places for percentage

        Returns:
            Percentage as Decimal (e.g., 15.00)
        """
        try:
            val = Decimal(str(value)) * Decimal('100')
            return BaseCalculator.round_decimal(val, decimal_places)
        except (ValueError, TypeError):
            return Decimal('0')

    @staticmethod
    def from_percentage(percentage: Union[Decimal, float, int]) -> Decimal:
        """
        Convert percentage to ratio

        Args:
            percentage: Percentage value (e.g., 15 for 15%)

        Returns:
            Ratio as Decimal (e.g., 0.15)
        """
        try:
            return Decimal(str(percentage)) / Decimal('100')
        except (ValueError, TypeError):
            return Decimal('0')

    @staticmethod
    def is_zero(value: Union[Decimal, float, int],
               tolerance: Decimal = Decimal('0.01')) -> bool:
        """
        Check if value is effectively zero within tolerance

        Args:
            value: Value to check
            tolerance: Acceptable deviation from zero

        Returns:
            True if value is within tolerance of zero
        """
        try:
            val = abs(Decimal(str(value)))
            return val <= tolerance
        except (ValueError, TypeError):
            return True

    @staticmethod
    def clamp(value: Union[Decimal, float, int],
             min_value: Optional[Union[Decimal, float, int]] = None,
             max_value: Optional[Union[Decimal, float, int]] = None) -> Decimal:
        """
        Clamp value between min and max

        Args:
            value: Value to clamp
            min_value: Minimum value (None for no minimum)
            max_value: Maximum value (None for no maximum)

        Returns:
            Clamped Decimal value
        """
        try:
            val = Decimal(str(value))

            if min_value is not None:
                val = max(val, Decimal(str(min_value)))

            if max_value is not None:
                val = min(val, Decimal(str(max_value)))

            return val
        except (ValueError, TypeError):
            return Decimal('0')

    @staticmethod
    def safe_sum(*values: Union[Decimal, float, int]) -> Decimal:
        """
        Safely sum values, treating None and errors as zero

        Args:
            *values: Values to sum

        Returns:
            Sum as Decimal
        """
        total = Decimal('0')
        for value in values:
            try:
                if value is not None:
                    total += Decimal(str(value))
            except (ValueError, TypeError):
                continue
        return total

    @staticmethod
    def days_in_year(days: int = 360) -> int:
        """
        Get number of days to use for annual calculations
        Default: 360 (financial year convention)
        """
        return days

    @staticmethod
    def format_currency(value: Union[Decimal, float, int],
                       symbol: str = "€") -> str:
        """
        Format value as currency

        Args:
            value: Value to format
            symbol: Currency symbol

        Returns:
            Formatted string
        """
        try:
            val = Decimal(str(value))
            formatted = f"{val:,.2f}"
            return f"{symbol}{formatted}"
        except (ValueError, TypeError):
            return f"{symbol}0.00"

    @staticmethod
    def format_percentage(value: Union[Decimal, float, int],
                         decimal_places: int = 2) -> str:
        """
        Format value as percentage

        Args:
            value: Ratio value (e.g., 0.15 for 15%)
            decimal_places: Decimal places

        Returns:
            Formatted percentage string
        """
        try:
            pct = BaseCalculator.to_percentage(value, decimal_places)
            return f"{pct}%"
        except (ValueError, TypeError):
            return "0.00%"

    @staticmethod
    def validate_positive(value: Union[Decimal, float, int],
                         field_name: str = "Value") -> Decimal:
        """
        Validate that value is positive

        Args:
            value: Value to validate
            field_name: Name for error message

        Returns:
            Validated Decimal value

        Raises:
            CalculationError if value is negative
        """
        try:
            val = Decimal(str(value))
            if val < 0:
                raise CalculationError(f"{field_name} must be positive, got {val}")
            return val
        except (ValueError, TypeError) as e:
            raise CalculationError(f"Invalid {field_name}: {e}")

    @staticmethod
    def validate_range(value: Union[Decimal, float, int],
                      min_val: Union[Decimal, float, int],
                      max_val: Union[Decimal, float, int],
                      field_name: str = "Value") -> Decimal:
        """
        Validate that value is within range

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            field_name: Name for error message

        Returns:
            Validated Decimal value

        Raises:
            CalculationError if value is out of range
        """
        try:
            val = Decimal(str(value))
            min_v = Decimal(str(min_val))
            max_v = Decimal(str(max_val))

            if val < min_v or val > max_v:
                raise CalculationError(
                    f"{field_name} must be between {min_v} and {max_v}, got {val}"
                )
            return val
        except (ValueError, TypeError) as e:
            raise CalculationError(f"Invalid {field_name}: {e}")
