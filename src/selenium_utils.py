import textwrap
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

class SeleniumUtils:
    DRIVER_TIMEOUT_SECONDS = 120
    EMPTY_HTML_DOCUMENT = "<html><head></head><body></body></html>"

    def __init__(self):
        self.driver = self._initialize_driver()
        self.url = None

    def _initialize_driver(self):
        driver = webdriver.Chrome(options=Options())
        driver.set_window_size(1920, 1080)
        driver.implicitly_wait(self.DRIVER_TIMEOUT_SECONDS)
        return driver

    def _load_initial_page(self):
        try:
            self.driver.get(self.url)
        except WebDriverException:
            raise Exception(f"URL '{self.url}' is not reachable.")
        if self.driver.page_source == self.EMPTY_HTML_DOCUMENT:
            raise Exception(f"URL '{self.url}' is not reachable.")

    def connect_driver(self, url):
        self.url = url
        try:
            self._load_initial_page()
        except Exception as e:
            if self.driver:
                print("SeleniumUtils.connect_driver -> Disconnecting driver")
                self.driver.quit()
            raise e

    def close_local_driver(self):
        if self.driver is None:
            print("SeleniumUtils.close_local_driver -> The driver is already closed.")
        else:
            self.driver.quit()
            self.driver = None

    def go_to_url(self, url):
        self.url = url
        self._load_initial_page()

    def _assert_element_id_exists(self, action):
        if action.element_id == '':
            raise Exception("Action cannot be executed without a element_id")

    def _click_element(self, element_id):
        try:
            self.driver.find_element(By.ID, element_id).click()
            print("SeleniumUtils._click_element -> css id: " + element_id)
        except:
            raise NoSuchElementException("SELENIUM: Could not click on the element with the id: " + element_id)

    def _enter_text_in_element(self, element_id, text):
        try:
            element = self.driver.find_element(By.ID, element_id)
            element.send_keys(text)
            print("SeleniumUtils._enter_text_in_element -> element_id " + element_id)
        except:
            raise NoSuchElementException("SELENIUM: Could not enter text in the element with the id: " + element_id)

    def execute_action_for_prompt(self, content) -> bool:
        try:
            if content.action == "click":
                self._assert_element_id_exists(content)
                self._click_element(content.element_id)

            elif content.action == "enter_text":
                self._assert_element_id_exists(content)
                self._enter_text_in_element(content.element_id, content.text)

            elif content.action == "key_enter":
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ENTER).perform()

            elif content.action == "scroll":
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)

            elif content.action == "finish":
                return False
            
            elif content.action == "error":
                raise Exception("Failed to execute action, Generative AI cannot give action")

            return True

        except NoSuchElementException as ex:
            print(f"SeleniumUtils.execute_action_for_prompt -> Failed to find element {content.element_id}: {ex}")
            raise Exception("Failed to execute action, Generative AI returned invalid action")
        except Exception as ex:
            print(f"SeleniumUtils.execute_action_for_prompt -> Failed to execute prompt action: {ex}")
            raise Exception("Failed to execute action generative AI action")

    def assign_auto_generated_ids(self):
        js_script = textwrap.dedent("""
                function getElementXPath(element) {
                    if (element.id) {
                        return 'id("' + element.id + '")';
                    }
                    var parts = [];
                    while (element && element.nodeType === Node.ELEMENT_NODE && element.tagName.toLowerCase() !== 'html') {
                        var index = 1;
                        var sibling = element.previousSibling;
                        while (sibling) {
                            if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === element.tagName) {
                                index++;
                            }
                            sibling = sibling.previousSibling;
                        }
                        var tagName = element.tagName.toLowerCase();
                        var part = tagName + '[' + index + ']';
                        parts.unshift(part);
                        element = element.parentNode;
                    }
                    return '/html/' + parts.join('/');
                }
                                    
                function getElementDeepIndex(element) {
                    if (element.id) {
                        return 'id("' + element.id + '")';
                    }
                    var parts = [];
                    while (element && element.nodeType === Node.ELEMENT_NODE && element.tagName.toLowerCase() !== 'html') {
                        var deepIndex = 1;
                        var sibling = element.previousSibling;
                        while (sibling) {
                            if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === element.tagName) {
                                deepIndex++;
                            }
                            sibling = sibling.previousSibling;
                        }
                        var tagName = element.tagName.toLowerCase() + deepIndex;
                        element = element.parentNode;
                    }
                    return '/html/' + tagName;
                }

                function getElementText(el) {
                    if (el.tagName.toLowerCase() === 'input') {
                        return el.name || '';
                    }
                    if (el.tagName.toLowerCase() === 'textarea') {
                        return el.value || '';
                    }
                    return el.textContent.trim();
                }

                const elements = document.querySelectorAll('li, button, input, textarea, [type=text], a');
                elements.forEach((el) => {
                    var xpath = getElementDeepIndex(el);
                    var text = getElementText(el);
                    var idValue = xpath.replace(/[^a-zA-Z0-9_\\-]/g, '_');
                    if (text) {
                        idValue += '_' + text.replace(/[^a-zA-Z0-9_\\-]/g, '_').substring(0, 32);
                    }
                    el.id = idValue;
                });
                """).strip()
        
                # const elements = document.querySelectorAll('li, button, input, textarea, [type=text], a');
                # elements.forEach((el) => {
                #     var xpath = getElementXPath(el);
                #     el.id = xpath.replace(/[^a-zA-Z0-9_\\-]/g, '_');
                # });
                # """).strip()

        self.driver.execute_script(js_script)

    def get_visible_dom(self):
        js_script = textwrap.dedent("""

                function isElementInViewport(el) {
                    var rect = el.getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                    );
                }

                function isElementVisible(el) {
                    return el.offsetWidth > 0 && el.offsetHeight > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                }


                var allElements = document.querySelectorAll('body *');
                var visibleElements = Array.from(allElements)
                    .filter(el => isElementInViewport(el) && isElementVisible(el));

                // Filter out child elements
                var filteredElements = visibleElements.filter(el => {
                    return !visibleElements.some(parentEl => parentEl !== el && parentEl.contains(el));
                });

                var visibleElementsHtml = filteredElements.map(el => el.outerHTML).join('\\n');
                return visibleElementsHtml;

                """).strip()

        return str(self.driver.execute_script(js_script))