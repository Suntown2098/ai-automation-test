import logging
import time
import uuid
from cachetools import TTLCache
from src.selenium_utils import SeleniumUtils
from src.dom_analyzer import DomAnalyzer
from src.config import MARKDOWN_INPUT, USER_PROMPT


class AgentProcessor:
    def __init__(self, url):
        self.cache_test_case = TTLCache(maxsize=1000, ttl=3600) # {'<module>, <view>, <button>', <steps>, <result>}
        self.log_cache = TTLCache(maxsize=1000, ttl=3600)
        self.cache_dom = TTLCache(maxsize=1000, ttl=3600) # {<task_id>, <dom_metadata>, <dom>}

        self.driver = None
        self.url = None
        self.dom_analyzer = DomAnalyzer()

        self.selenium_utils = SeleniumUtils()
        self.selenium_utils.connect_driver(url)

    def parse_user_prompt(self, user_prompt, markdown):
        user_content = USER_PROMPT.replace("@@@task@@@", user_prompt)
        markdown_content = MARKDOWN_INPUT.replace("@@@markdown@@@", markdown)
        return user_content + "\n" + markdown_content

    def execute_cached_prompt(self, user_prompt, markdown):
        pass

    def execute_non_cached_prompt(self, action):
        pass

    def execute_prompt(self, prompt):
        if prompt == "":
            print("Empty prompt.")
            return True

        session_id = str(uuid.uuid4())

        accumulated_actions = []
        current_step = 0

        last_action = None
        consecutive_action_count = 1
        consecutive_failure_count = 0
        is_duplicate = False
        is_valid = True

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

            if not visible_dom:
                raise Exception("Failed to get visible DOM")

            # Set metadata cho DOM
            dom_metadata = self.dom_analyzer.set_metadata(visible_dom)

            # Nếu metadata đã có trong cache thì lấy từ cache
            if dom_metadata in self.dom_cache:
                pass
            else:
                # Lưu DOM metadata vào cache
                self.dom_cache[dom_metadata] = visible_dom

                # Summarize DOM
                dom_summary = self.dom_analyzer.summarize_dom(visible_dom)

                try:
                    # Lấy LLM response for next action
                    response = self.dom_analyzer.get_actions(session_id, prompt, visible_dom, accumulated_actions,
                                                             is_duplicate, is_valid, last_action)

                except Exception as ex:
                    logging.error("Failed to get Action from Generative AI model: %s", ex)
                    raise Exception("Failed to get Action from Generative AI model")

            if not response.steps:
                consecutive_failure_count += 1
                last_action = None
                continue




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


