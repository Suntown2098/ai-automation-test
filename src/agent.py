import time
import uuid
from cachetools import TTLCache
from pydantic import BaseModel, ValidationError, validator
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


    def generate_prompt(self, user_prompt, markdown, is_valid, is_duplicate) -> str:
        '''
        1. Nếu is_valid_step = False thì generate resolving prompt 
        2. Nếu is_duplicate_step = True thì generate resolving prompt
        3. Nếu none of the above thì generate follow up prompt
        '''
        if is_valid == False:
            pass

        elif is_duplicate == True:
            pass

        user_content = USER_PROMPT.replace("@@@task@@@", user_prompt)
        markdown_content = MARKDOWN_INPUT.replace("@@@markdown@@@", markdown)
        return user_content + "\n" + markdown_content

    def resolve_follow_up(self, duplicate, valid, formatted, id_used, last_action,  executed_actions_str, task, variables_string):
        if id_used is False:
            return f"Please note that action {last_action} you provided does not use css id, the needed element has an id," \
                   f" can you try again and provide the id as css_selector instead"
        if formatted is False:
            return f"Please note that the last action you provided is not in the required json format," \
                   f" The output format should be {{\"steps\":[{{ \"action\":..,\"css_selector\":...., \"text\":..., \"explanation\":..., \"description\":...}}]}}, if task is achieved return finish action"

        if valid is False:
            return f"Please note that the last action you provided is invalid or not interactable in selenium," \
                   f" so i need another way to perform the task"

        if duplicate is True:
            return f"Please note that the last action you provided is duplicate," \
                   f" I need the next action to perform the task"

        return f"Actions Executed so far are \n {executed_actions_str}\n " \
               f"please provide the next action to achieve the task delimited by triple quotes:" \
               f" \"\"\"{task} or return finish action if the task is completed\"\"\"\n {variables_string}"

    def execute_task(self, task: str) -> None:
        if task == "":
            print("Empty prompt.")
            return True

        # session_id = str(uuid.uuid4())
        current_step = 0
        consecutive_action_count = 1
        consecutive_failure_count = 0
        is_duplicate_step = False
        is_valid_step = True
        step = None
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
                user_prompt = self.generate_prompt(self, task, markdown, is_valid_step, is_duplicate_step) # Tạo prompt và gọi LLM
                step = self.model.get_action(user_prompt)
            # except ValidationError as e: # llm response có follow TestStep structure không?
            #     consecutive_failure_count += 1
            #     continue
            except Exception as e:
                raise Exception("AgentProcessor.execute_task -> Failed to get model response")
            
            current_step += 1

            ######### START Update consecutive_action_count và is_duplicate_step #########
            # Kiểm tra is first step và is duplicated step?
            if not len(accumulated_steps) or accumulated_steps[-1].action != step.action:
                consecutive_action_count = 1
                is_duplicate_step = False
            else:
                consecutive_action_count += 1
                is_duplicate_step = True
                continue
            ######### END Update consecutive_action_count và is_duplicate_step #########
            

            ######### START Update consecutive_failure_count và is_valid_step #########
            # Execute action, nếu báo lỗi thì retry
            try:
                is_finish = self.selenium_utils.execute_action_for_prompt(step) # Thực hiện action
            except Exception:
                is_valid_step = False
                consecutive_failure_count += 1
                continue

            # Kiểm tra execute_result?
            if is_finish: ## Nếu là finish thì thoát while loop
                break 

            consecutive_failure_count = 0
            is_valid_step = True
            accumulated_steps.append(step)
            ######### END Update consecutive_failure_count và is_valid_step #########
                
        if not len(accumulated_steps):
            raise Exception("No actions were executed")
