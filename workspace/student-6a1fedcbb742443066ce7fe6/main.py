# Simple Interactive Calculator (Python)
# Run:  python main.py

def main():
    a = float(input("Enter first number: "))
    op = input("Enter operator (+, -, *, /): ")
    b = float(input("Enter second number: "))

    if op == "+":
        result = a + b
    elif op == "-":
        result = a - b
    elif op == "*":
        result = a * b
    elif op == "/":
        result = a / b if b != 0 else "Error: division by zero"
    else:
        result = "Error: unknown operator"

    print("Result:", result)


if __name__ == "__main__":
    main()
