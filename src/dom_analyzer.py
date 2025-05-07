import time
from bs4 import BeautifulSoup, Comment
from markdownify import markdownify as md

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

    def clean_markdown(self, markdown):
        # Remove base64 encoded images
        cleaned_markdown = re.sub(r'!\[[^\]]*\]\(data:image\/[a-zA-Z]+;base64,[^\)]+\)', '', markdown)

        # Remove CSS styles - targeting patterns that start with a period or within style tags
        cleaned_markdown = re.sub(r'<style>[\s\S]*?<\/style>', '', cleaned_markdown)

        # Remove excessive whitespace
        cleaned_markdown = re.sub(r'\n\s*\n', '\n\n', cleaned_markdown)

        return cleaned_markdown

    def convert_to_md(self, html_doc):

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
