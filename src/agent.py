import time
import uuid
import hashlib
from cachetools import TTLCache
from src.selenium_utils import SeleniumUtils
from src.dom_analyzer import DomAnalyzer
from src.model import Model
from src.config import MARKDOWN_INPUT, DEFAULT_USER_PROMPT, FOLLOW_UP_PROMPT, RESOLVE_DUPLICATED_STEP_PROMPT, RESOLVE_INVALID_STEP_PROMPT


class AgentProcessor:
    def __init__(self, url):
        self.cache_test_case = TTLCache(maxsize=1000, ttl=3600) # {'<module>, <view>, <button>', <steps>, <result>}
        self.log_cache = TTLCache(maxsize=1000, ttl=3600)
        self.dom_cache = TTLCache(maxsize=1000, ttl=3600) # {<task_id>, <dom_metadata>, <dom>}

        self.dom_analyzer = DomAnalyzer()
        self.model = Model()
        self.selenium_utils = SeleniumUtils()
        self.selenium_utils.connect_driver(url)


    def generate_prompt(self, task, markdown, is_valid, executed_steps=[], last_step=None) -> str:
        '''
        1. Nếu is_valid_step = False thì generate resolving prompt 
        2. Nếu is_duplicate_step = True thì generate resolving prompt
        3. Nếu none of the above thì generate follow up prompt
        '''
        markdown_content = MARKDOWN_INPUT.replace("@@@markdown@@@", markdown)
        if not last_step:
            user_content = DEFAULT_USER_PROMPT.replace("@@@task@@@", task)
        else:
            if is_valid == False:
                user_content = RESOLVE_INVALID_STEP_PROMPT.replace("@@@last_step@@@", last_step).replace("@@@task@@@", task)
            else:
                executed_steps_description = str([step.description for step in executed_steps])
                user_content = FOLLOW_UP_PROMPT.replace("@@@executed_steps@@@", str(executed_steps)).replace("@@@task@@@", task)

        return user_content + "\n" + markdown_content

    def execute_task(self, task: str) -> None:
        if task == "":
            print("Empty prompt.")
            return

        # session_id = str(uuid.uuid4())
        current_step = 0
        consecutive_action_count = 1
        consecutive_failure_count = 0
        # is_duplicate_step = False
        is_valid_step = True
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

            ### Hash DOM and save to cache -> Hash DOM ko work vì case: cùng 1 màn hình, sau khi chọn value cho field A thì value của field B sẽ biến đổi theo, nên cần lấy DOM mới liên tục
            # dom_hash = hashlib.sha256(visible_dom.encode('utf-8')).hexdigest()
            # if dom_hash not in self.dom_cache:
            #     # Get DOM metadata
            #     # dom_metadata = self.dom_analyzer.set_dom_metadata(visible_dom)
            #     self.dom_cache[dom_hash] = {"dom_metadata": {}, "dom": visible_dom}


            markdown = self.dom_analyzer.convert_to_md(visible_dom)

            try:
                user_prompt = self.generate_prompt(task, markdown, is_valid_step, accumulated_steps, last_step) # Tạo prompt và gọi LLM
                step = self.model.get_action(user_prompt)
            except Exception as e:
                raise Exception("AgentProcessor.execute_task -> Failed to get model response")
            
            current_step += 1

            ######### START Update consecutive_action_count và is_duplicate_step #########
            # Kiểm tra is first step and duplicated step?
            # if not len(accumulated_steps):
            #     consecutive_action_count = 1
            #     # is_duplicate_step = False
            # else:
            #     consecutive_action_count += 1
            #     # is_duplicate_step = True
            #     continue
            ######### END Update consecutive_action_count và is_duplicate_step #########
            

            ######### START Update consecutive_failure_count và is_valid_step #########
            # Execute action, nếu báo lỗi thì retry
            try:
                continue_execute = self.selenium_utils.execute_action_for_prompt(step) # Thực hiện action
            except Exception:
                is_valid_step = False
                consecutive_failure_count += 1
                continue

            # Kiểm tra execute_result?
            if not continue_execute: ## Nếu là finish thì thoát while loop
                break 

            consecutive_failure_count = 0
            is_valid_step = True
            accumulated_steps.append(step)
            last_step = step
            ######### END Update consecutive_failure_count và is_valid_step #########
                
        if not len(accumulated_steps):
            raise Exception("No actions were executed")
