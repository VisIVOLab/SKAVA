"""Allow ``python -m skava_publisher`` as a fallback to the entry-point script."""
from skava_publisher.cli import main

if __name__ == "__main__":
    main()
