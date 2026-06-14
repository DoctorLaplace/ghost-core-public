def add_two_numbers(a, b):
    return a + b

def TEST():
    return add_two_numbers(2, 3) == 5

if __name__ == "__main__":
    import sys
    sys.exit(0 if TEST() else 1)


if __name__ == "__main__":
    import sys
    try:
        sys.exit(0 if TEST() else 1)
    except Exception as e:
        sys.stderr.write(str(e))
        sys.exit(1)
