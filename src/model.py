import os
from pathlib import Path
from typing import List, Literal, Optional
import time
from pydantic import BaseModel, ValidationError, validator
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from src.config import DEFAUL_SYSTEM_PROMPT
from dotenv import load_dotenv


class TestStep(BaseModel):
    action: Literal["click", "enter_text", "key_enter", "scroll", "error", "finish"]
    css_selector: str
    text: str
    description: str

    def __eq__(self, other):
        if not isinstance(other, TestStep):
            return NotImplemented
        return self.action == other.action and self.text == other.text


class Model:
    # Load environment variables from .env file
    path_to_env_file = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=path_to_env_file, verbose = True)

    gpt_api_key = os.getenv("OPENAI_API_KEY")
    gpt_model = os.getenv("GPT_MODEL", "o4-mini")

    def __init__(self):
        self.system_prompt = DEFAUL_SYSTEM_PROMPT

    def get_action(self, user_prompt: str) -> Optional[TestStep]:
        # Instantiate OpenAI client
        llm_model = OpenAIModel(
            model_name='o4-mini',
            provider=OpenAIProvider(api_key=self.gpt_api_key)
        )

        # Create a new agent
        agent = Agent(
            llm_model,
            output_type=TestStep,
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
