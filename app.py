import sys

# Check for correct number of arguments
if len(sys.argv) != 4:
    print("Usage: python sum_subtract.py <num1> <+ or -> <num2>")
    sys.exit(1)

try:
    num1 = float(sys.argv[1])
    operator = sys.argv[2]
    num2 = float(sys.argv[3])

    if operator == "+":
        result = num1 + num2
    elif operator == "-":
        result = num1 - num2
    else:
        print("Unsupported operator. Use '+' or '-'.")
        sys.exit(1)

    print(f"Result: {result}")

except ValueError:
    print("Invalid number format. Please enter valid numbers.")
    sys.exit(1)
