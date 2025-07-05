# In skills/unit_converter_skill.py
import re

def convert_units(app, value, from_unit, to_unit, **kwargs):
    """Converts a value from one unit to another."""
    try:
        val = float(value)
    except ValueError:
        return "Please provide a valid number to convert."

    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    # Conversion factors dictionary
    factors = {
        'meters': 1.0, 'm': 1.0,
        'kilometers': 1000.0, 'km': 1000.0,
        'feet': 0.3048, 'ft': 0.3048,
        'miles': 1609.34, 'mi': 1609.34,
        'kilograms': 1.0, 'kg': 1.0,
        'pounds': 0.453592, 'lbs': 0.453592,
    }

    # Temperature conversion requires special formulas
    if from_unit in ['celsius', 'c'] and to_unit in ['fahrenheit', 'f']:
        result = (val * 9/5) + 32
        return f"{val}° Celsius is {result:.1f}° Fahrenheit."
    if from_unit in ['fahrenheit', 'f'] and to_unit in ['celsius', 'c']:
        result = (val - 32) * 5/9
        return f"{val}° Fahrenheit is {result:.1f}° Celsius."

    # Standard unit conversion using factors
    if from_unit in factors and to_unit in factors:
        # Convert 'from_unit' to base unit (meters or kg), then to 'to_unit'
        result = val * factors[from_unit] / factors[to_unit]
        return f"{value} {from_unit} is equal to {result:.2f} {to_unit}."
    
    return f"I'm sorry, I don't know how to convert between {from_unit} and {to_unit}."

def register():
    """Registers the unit conversion command with regex."""
    return {
        'convert_units': {
            'handler': convert_units,
            # This regex captures the number, from_unit, and to_unit
            'regex': r'convert (\d+\.?\d*|\d+) (.+?) to (.+)',
            'params': ['value', 'from_unit', 'to_unit']
        }
    }