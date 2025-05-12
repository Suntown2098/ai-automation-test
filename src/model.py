import os
from pathlib import Path
from typing import List, Dict, Any, Literal, Optional
import time
import logging
from pydantic import BaseModel, ValidationError, validator
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from prompt.config import DEFAUL_SYSTEM_PROMPT
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Step(BaseModel):
    action: Literal["click", "text-enter", "key_enter", "scroll", "error", "finish"]
    element_id: str
    text: str
    component_name: str
    description: str

class TestSteps(BaseModel):
    steps: List[Step]


class Model:
    # # Load environment variables from .env file
    # path_to_env_file = Path(__file__).parent.parent / '.env'
    # load_dotenv(dotenv_path=path_to_env_file, verbose = True)

    gpt_api_key = os.getenv("OPENAI_API_KEY")
    gpt_model = os.getenv("GPT_MODEL", "o4-mini")

    def __init__(self):
        # Load the system prompt from ui_testing_prompt.txt
        prompt_file_path = Path(__file__).parent.parent / 'src' / 'prompt' / 'ui_testing_prompt.txt'
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as file:
                self.system_prompt = file.read()
        except FileNotFoundError:
            logger.error(f"System prompt file not found at {prompt_file_path}")
            self.system_prompt = ""  # Fallback to an empty prompt
        except Exception as e:
            logger.error(f"Error reading system prompt file: {e}")
            self.system_prompt = ""  # Fallback to an empty prompt

    def get_action(self, user_prompt: str) -> Optional[TestSteps]:
        # Instantiate OpenAI client
        llm_model = OpenAIModel(
            model_name='o4-mini',
            provider=OpenAIProvider(api_key=self.gpt_api_key)
        )

        # Create a new agent
        agent = Agent(
            llm_model,
            output_type=TestSteps,
            system_prompt=self.system_prompt
        )

        max_retries = 5
        attempts = 0
        # formatted = True
        # css_id_used = True

        while True:
            if attempts > max_retries:
                raise Exception("Model.get_action -> Max retries reached")
            try:
                result = agent.run_sync(user_prompt)
                return result.output
            except ValidationError as e: # llm response có follow TestStep structure không?
                print("Model.get_action -> Validation error:", e)
            except Exception as e:
                print("Model.get_action -> An error occurred:", e)
    
            attempts += 1
            time.sleep(1)
