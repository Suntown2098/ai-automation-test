import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import time
from task_executor import TaskExecutor

def main():
    test_url = "https://swm-dev.smartlogvn.com/"

    try:
        processor = TaskExecutor(test_url)

        # Test steps
        # processor.execute_task("Test tạo đơn hàng nhận cho tao")
        steps= [
            "Đăng nhập vào hệ thống với tài khoản ‘toshiba-huy1’ và password ‘123’",
            "Chọn Module INBOUND trên navigation bar, sau đó click submenu ASN/Receipt trên thanh điều hướng",
            "Nhấn nút 'ASN' để chuyển sang màn hình Receipt Detail",

        ]
        for step in steps:
            print(f"Executing step: {step}")
            processor.execute_task(step)
            time.sleep(1)  # Sleep to simulate time taken for each step

        time.sleep(1)
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
