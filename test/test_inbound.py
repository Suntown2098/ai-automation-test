import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import time
from agent import AgentProcessor


def main():
    test_url = "https://swm.danghung.xyz/login/"

    try:
        processor = AgentProcessor(test_url)

        # Test steps
        processor.execute_task("login with username 'tbs-qa' and password '123'")
        time.sleep(1)
        processor.execute_task("go to module inbound and click on view asn/receipt")
        time.sleep(1)
        processor.execute_task("click button 'asn' to create new asn")
        time.sleep(1)
        processor.execute_task("in tab General, select OWNER = 'CEVA'")
        time.sleep(1)
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
