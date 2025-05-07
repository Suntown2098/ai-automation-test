/import time
import uuid
from cachetools import TTLCache
from src.selenium_utils import SeleniumUtils
from src.dom_analyzer import DomAnalyzer
from src.gpt_client import GptClient
from src.config import MARKDOWN_INPUT, USER_PROMPT


class AgentProcessor:
    def __init__(self, url):
        self.cache_test_case = TTLCache(maxsize=1000, ttl=3600) # {'<module>, <view>, <button>', <steps>, <result>}
        self.log_cache = TTLCache(maxsize=1000, ttl=3600)
        self.cache_dom = TTLCache(maxsize=1000, ttl=3600) # {<task_id>, <dom_metadata>, <dom>}

        self.driver = None
        self.url = None
        self.dom_analyzer = DomAnalyzer()
        self.model = GptClient()

        self.selenium_utils = SeleniumUtils()
        self.selenium_utils.connect_driver(url)

    def generate_prompt(self, user_prompt, markdown):
        user_content = USER_PROMPT.replace("@@@task@@@", user_prompt)
        markdown_content = MARKDOWN_INPUT.replace("@@@markdown@@@", markdown)
        return user_content + "\n" + markdown_content

    def execute_cached_prompt(self, user_prompt, markdown):
        pass

    def execute_non_cached_prompt(self, action):
        pass

    def execute_task(self, task: str) -> None:
        if task == "":
            print("Empty prompt.")
            return True

        session_id = str(uuid.uuid4())
        current_step = 0
        consecutive_action_count = 1
        consecutive_failure_count = 0
        is_duplicate_step = False
        is_valid_step = True
        step = None
        last_step = None
        accumulated_steps = []

        while True:
            # Nếu lặp lai TestSteps >5  lần hoặc Error > 5 lần hoặc thực hiện hơn 100 TestSteps thì dừng
            if consecutive_action_count > 5:
                raise Exception("Generative AI is stuck at the same action, please try again")
            if consecutive_failure_count > 5:
                raise Exception("Generative AI generated invalid actions consecutively, please try again")
            if current_step > 100:
                break

            # Gán id tự động cho các phần tử trong DOM
            self.selenium_utils.assign_auto_generated_ids()
            
            # Lấy DOM hiện tại
            visible_dom = self.selenium_utils.get_visible_dom()

            markdown = self.dom_analyzer.convert_to_md(visible_dom)

            # if not visible_dom:
            # Set metadata cho DOM
            # Nếu metadata đã có trong cache thì lấy từ cache

            try:
                # Tạo prompt và gọi LLM
                user_prompt = self.generate_prompt(self, task, markdown)
                step = self.model.get_action(user_prompt)
            except Exception as ex:
                raise Exception("AgentProcessor.execute_task -> Failed to get model response")

            # Kiểm tra llm response có follow TestStep structure không? 
            if not step: ## Nếu có (action == None) thì tăng consecutive_failure_count và retry
                consecutive_failure_count += 1
                last_action = None
                continue
            else: 
                # Kiểm tra is first action?
                if not len(last_step):
                    consecutive_action_count = 1
                    is_duplicate_step = False
                else:
                    # Nếu not first action (len action_chain > 0) thì kiểm tra is duplicate step?
                    if accumulated_steps[-1].action == step.action:
                        consecutive_action_count += 1
                        is_duplicate_step = True
                        current_step += 1
                        continue
                
                execute_result = self.selenium_utils.execute_action_for_prompt(step) # Thực hiện action

                # Kiểm tra execute_result?
                if execute_result == 0: ## Nếu execute_result lỗi thì xóa accumulated_steps
                    accumulated_steps = []
                    break 
                elif execute_result == 2:
                    consecutive_failure_count += 1
                    last_action = None
                    continue
                consecutive_failure_count = 0

                accumulated_steps.append(step) # Add vào step chain




            index = 0

            # Check if the last action is a duplicate
            if last_action == response.steps[index]:
                consecutive_action_count += 1
                is_duplicate = True
                if consecutive_action_count > 5:
                    raise Exception("Generative AI is stuck at the same action, please try again")
                index += 1
                continue
            else:
                consecutive_action_count = 1
                is_duplicate = False

            step = response.steps[index]
            if step.action == "enter_text":
                try:
                    while not(0 <= index < len(response.steps) and response.steps[index].action == "enter_text"):
                        step = response.steps[index]
                        last_action = step
                        self._execute_action_for_prompt(step)
                        is_valid = True
                        consecutive_failure_count = 0
                        accumulated_actions.append(step)
                        index += 1

                    if index < len(response.steps) and response.steps[index].action == "key_enter":
                        time.sleep(1)
                        last_action = response.steps[index]
                        self._execute_action_for_prompt(response.steps[index])
                        is_valid = True
                        consecutive_failure_count = 0
                        accumulated_actions.append(step)
                        index += 1

                except Exception:
                    is_valid = False
                    consecutive_failure_count += 1
                    continue
            else:
                try:
                    last_action = step
                    if not self._execute_action_for_prompt(step):
                        break
                    is_valid = True
                    consecutive_failure_count = 0
                    accumulated_actions.append(step)
                except Exception:
                    is_valid = False
                    consecutive_failure_count += 1
                    continue

            time.sleep(3)

        if not accumulated_actions:
            raise Exception("No actions were executed")


