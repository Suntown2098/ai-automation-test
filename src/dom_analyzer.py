from src.md_converter import convert_to_md
from cachetools import TTLCache
from src.gpt_client import GptClient, TokenLimitExceededError, RateLimitExceededError
from src.config import SYSTEM_PROMPT, MARKDOWN_INPUT, USER_PROMPT
import re
import logging
import time
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def convert_keys_to_lowercase(data):
    if isinstance(data, dict):
        return {k.lower(): convert_keys_to_lowercase(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_keys_to_lowercase(item) for item in data]
    else:
        return data


class DomAnalyzer:
    def __init__(self, cache_ttl=3600, cache_maxsize=1000):
        self.cache = TTLCache(maxsize=1000, ttl=3600)
        self.log_cache = TTLCache(maxsize=1000, ttl=3600)
        self.md_cache = TTLCache(maxsize=1000, ttl=3600)
        self.gpt_client = GptClient()

    def get_actions(self, session_id, user_prompt, html_doc, actions_executed, duplicate=False, valid=True, last_action=None, user_input=None, system_input=None, return_history=False):
        markdown = convert_to_md(html_doc)

        system_content = USER_PROMPT
        user_content = USER_PROMPT.replace("@@@task@@@", user_prompt)
        markdown_content = MARKDOWN_INPUT.replace("@@@markdown@@@", markdown)

        max_retries = 5
        attempts = 0
        formatted = True
        id_used = True

        while attempts < max_retries:
            response = None
            first_step = None

            if session_id not in self.cache:
                system_content = {'role': 'system', 'message': system_input, 'removable': False}
                markdown_content = {'role': 'user', 'message': markdown_input, 'removable': False}
                user_content = {'role': 'user', 'message': user_input, 'removable': False}
                try:
                    final_user_prompt = user_content + markdown_content
                    response = self.gpt_client.make_request(final_user_prompt)
                    self.cache[session_id] = [system_content, markdown_content, user_content]
                    self.log_cache[session_id] = [system_content, {'role': 'user', 'message': html_doc, 'removable': False}, user_content]
                    self.md_cache[session_id] = markdown
                    extracted_response = self.extract_steps(response)
                    if not extracted_response or extracted_response == {}:  # Check if the response is empty
                        raise ValueError("Empty or invalid response")

                    first_step = extracted_response.get('steps', [{}])[0]  # Safely get the first step
                    if first_step.get('css_selector', '').find('#') == -1 and first_step.get('action') not in ['finish', 'error', 'scroll']:
                        raise ValueError("Condition not met: cssSelector does not use ID or action is not 'finish'")

                    if return_history is True:
                        extracted_response['history'] = self.md_cache[session_id]
                    return extracted_response

                except ValueError as e:
                    logging.warn(f"Failed with value error: {e}")
                    attempts += 1

                    # Check the specific error message to set formatted and id_used accordingly
                    if str(e) == "Condition not met: cssSelector does not use ID or action is not 'finish'":
                        formatted = True
                        id_used = False
                        last_action = first_step
                    else:
                        last_action = response
                        formatted = False
                        id_used = True  # Assuming the default state is that IDs are used
                    duplicate = False
                    # logging.info(f"Failed to get response, next attempt#{attempts}: {e}")
                    time.sleep(1)
                    continue  # Retry the loop
                except TokenLimitExceededError as e:
                    logging.error(f"Failed: {e} ")
                    if self.clean_prompt(self.cache[session_id]):
                        continue
                    break
                except RateLimitExceededError as e:
                    logging.error(f"Failed with rate limit exceeded: {e} "
                                  f"\n going to sleep for 10 seconds and try again")
                    formatted = True
                    attempts += 1
                    time.sleep(10)
                    continue
                except Exception as e:
                    formatted = True
                    attempts += 1
                    logging.warn(f"Failed to get response, next attempt#{attempts}: {e} ")
                    time.sleep(1)
                    continue
            else:
                executed_actions_str = '\n'.join([f"{idx+1}.{self.format_action(action)}" for idx, action in enumerate(actions_executed)])
                follow_up = self.resolve_follow_up(duplicate, valid, formatted, id_used, self.format_action(last_action), executed_actions_str, user_prompt, variables_string)
                if markdown == self.md_cache[session_id]:
                    prefix_message = f"Again, Here is the markdown representation of the currently visible section of the page on which you will execute the actions: {markdown}\n\n" if attempts == max_retries-1 else ""
                    prefix_message_log = f"Again, Here is the markdown representation of the currently visible section of the page on which you will execute the actions: {html_doc}\n\n" if attempts == max_retries-1 else ""
                    if not id_used or not formatted:
                        follow_up_content = [{'role': 'user', 'message': f"{prefix_message}{follow_up}", 'removable': True}]
                        assistant_content = {'role': 'assistant', 'message': self.format_action(last_action), 'removable': True}
                        follow_up_content_log = [{'role': 'user', 'message': f"{prefix_message_log}{follow_up}", 'removable': True}]
                    else:
                        follow_up_content = [{'role': 'user', 'message': f"{prefix_message}{follow_up}", 'removable': False}]
                        assistant_content = {'role': 'assistant', 'message': self.format_action(last_action), 'removable': False}
                        follow_up_content_log = [{'role': 'user', 'message': f"{prefix_message_log}{follow_up}", 'removable': False}]
                else:
                    follow_up_content = [{'role': 'user', 'message': f"Here is the new markdown "
                                                                     f"representation of the currently visible section of the page on which you will execute the actions: "
                                                                     f"{markdown}\n\n{follow_up}", 'removable': False}]
                    follow_up_content_log = [{'role': 'user', 'message': f"Here is the new markdown: {html_doc}\n\n{follow_up}"}]
                    assistant_content = {'role': 'assistant', 'message': self.format_action(last_action), 'removable': False}
                    self.md_cache[session_id] = markdown

                # add assistant_content, follow_up_content to the cache

                try:
                    response = self.gpt_client.make_request([*self.cache[session_id], assistant_content, *follow_up_content])
                    self.cache[session_id].append(assistant_content)
                    self.cache[session_id].extend(follow_up_content)

                    self.log_cache[session_id].append(assistant_content)
                    self.log_cache[session_id].extend(follow_up_content_log)

                    extracted_response = self.extract_steps(response)

                    if not extracted_response or extracted_response == {}:
                        raise ValueError("Empty or invalid response")

                    first_step = extracted_response.get('steps', [{}])[0]  # Safely get the first step
                    if first_step.get('css_selector', '').find('#') == -1 and first_step.get('action') not in ['finish', 'error', 'scroll']:
                        raise ValueError("Condition not met: cssSelector does not use ID or action is not 'finish'")
                    if return_history is True:
                        extracted_response['history'] = self.md_cache[session_id]

                    return extracted_response

                except ValueError as e:
                    logging.warn(f"Failed with value error: {e}")
                    attempts += 1
                    last_action = response
                    # Check the specific error message to set formatted and id_used accordingly
                    if str(e) == "Condition not met: cssSelector does not use ID or action is not 'finish'":
                        formatted = True
                        id_used = False
                    else:
                        formatted = False
                        id_used = True  # Assuming the default state is that IDs are used
                    duplicate = False
                    # logging.info(f"Failed to get response, next attempt#{attempts}: {e}")
                    time.sleep(1)
                    continue  # Retry the loop
                except TokenLimitExceededError as e:
                    logging.error(f"Failed: {e} ")
                    if self.clean_prompt(self.cache[session_id]):
                        continue
                    break
                except RateLimitExceededError as e:
                    logging.error(f"Failed with rate limit exceeded: {e} "
                                  f"\n going to sleep for 10 seconds and try again")
                    formatted = True
                    attempts += 1
                    time.sleep(10)
                    continue
                except Exception as e:
                    attempts += 1
                    logging.info(f"Failed to get response, next attempt#{attempts}: {e} ")
                    time.sleep(1)
                    continue
        if return_history is True:
            extracted_response['history'] = self.md_cache[session_id]
        return {"steps": [{"action": "Error", "text": "Failed to get action"}]}

    def format_action(self, action):
        if action is None:
            return ""

        if isinstance(action, str):
            return action

        if isinstance(action, dict):
            return f"{{\"action\": \"{action['action']}\", \"css_selector\": \"{action['css_selector']}\", \"Text\": \"{action['text']}\", \"explanation\": \"{action['explanation']}\", \"description\": \"{action['description']}\"}}"

        return str(action)

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

    def extract_steps(self, json_str):
        try:
            data = json.loads(json_str)
            if 'steps' in data:
                return convert_keys_to_lowercase(data)
        except json.JSONDecodeError:
            pass
        pattern = r'(\{.*"steps".*\})'
        matches = re.findall(pattern, json_str, re.DOTALL)

        for match in matches:
            try:
                potential_json = match
                parsed_json = json.loads(potential_json)
                if 'steps' in parsed_json:
                    return convert_keys_to_lowercase(parsed_json)
            except json.JSONDecodeError as e:
                continue

        pattern = r'"steps":\s*\[(.*?\})\s*\]'
        matches = re.findall(pattern, json_str, re.DOTALL)

        # If matches are found, try to parse each one
        if matches:
            # Build a proper JSON string by enclosing the matched content in an array
            for match in matches:
                potential_json = '[' + match + ']'
                try:
                    # Attempt to parse the JSON
                    parsed_json = json.loads(potential_json)
                    # If successful, return the converted data
                    return convert_keys_to_lowercase({'steps': parsed_json})
                except json.JSONDecodeError as e:
                    logging.debug(f"Failed to parse JSON for matched steps: {e}")
                    continue

        logging.debug("No valid 'steps' array found or all parsing attempts failed.")
        return {}

    def print_prompt(self, session_id):
        logging.info("###########################################"
                     "###########################################")
        # logging.info(f"history: {self.log_cache[session_id]}")
        logging.info("###########################################"
                     "###########################################")

    def clean_prompt(self, prompt_history):
        # going to delete the first removable assistant/user prompt
        logging.info("Going to clean prompt history")
        if len(prompt_history) < 2:
            logging.info("History is less than 2 objects, will not attempt to clear")

        for i in range(len(prompt_history) - 1):
            if (prompt_history[i]['role'] == 'assistant' and prompt_history[i + 1]['role'] == 'user'
                 and prompt_history[i]['removable'] is True and prompt_history[i + 1]['removable'] is True):
                logging.info(f"Going to delete [{prompt_history[i]},\n{prompt_history[i + 1]}]")
                del prompt_history[i:i+2]
                return True
        logging.info("Was not able to find removable items")
        return False

    def clean_markdown(markdown):
        # Remove base64 encoded images
        cleaned_markdown = re.sub(r'!\[[^\]]*\]\(data:image\/[a-zA-Z]+;base64,[^\)]+\)', '', markdown)

        # Remove CSS styles - targeting patterns that start with a period or within style tags
        cleaned_markdown = re.sub(r'<style>[\s\S]*?<\/style>', '', cleaned_markdown)

        # Remove excessive whitespace
        cleaned_markdown = re.sub(r'\n\s*\n', '\n\n', cleaned_markdown)

        return cleaned_markdown

    def convert_to_md(html_doc):

        soup = BeautifulSoup(html_doc, 'html.parser')

        for element in soup(['script', 'style', 'iframe', 'noscript']):
            element.decompose()

        # Remove all comments, which includes CDATA
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        for tag in soup.find_all():
            for attr in ['href', 'src', 'xlink:href']:
                if attr in tag.attrs and 'base64,' in tag[attr].lower():
                    del tag[attr]

            if 'style' in tag.attrs:
                del tag['style']

        for li in soup.find_all('li'):
            a = li.find('a')
            if a:
                li.replace_with(a)

        for tag in soup.find_all(['li', 'button', 'input', 'textarea', 'a'], id=True):
            # Exclude hidden elements
            if tag.get('hidden') == 'true':
                continue
            # Initialize an empty list to hold the desired attributes
            desired_attributes = []

            if 'id' in tag.attrs:
                desired_attributes.append(f'id="{tag["id"]}"')

            include_attrs = {'aria-label',
                             'type',
                             'aria-current',
                             'aria-hidden',
                             'value',
                             'name',
                             'data-value',
                             'placeholder',
                             'role',
                             'title'
                             }

            for attr, value in tag.attrs.items():
                if attr in include_attrs:
                    desired_attributes.append(f'{attr}="{value}"')

            # Join the desired attributes into a single string
            attributes_str = ' '.join(desired_attributes)

            # Replace tag with a modified version that includes only the desired attributes
            tag.replace_with(f'<{tag.name}.postfix {attributes_str}>{tag.get_text()}</{tag.name}>')

        # Convert the modified HTML to Markdown
        markdown = md(str(soup), strip=['span'])
        markdown = re.sub(r'(\w+)\.postfix', r'\1', markdown)
        markdown = re.sub('\\s+', ' ', markdown)
        markdown = markdown.replace('\\_', '_')

        return clean_markdown(markdown)
