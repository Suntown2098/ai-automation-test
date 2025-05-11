import os
import json
import re
from typing import List, Dict, Any, Literal, Optional
from pathlib import Path
import logging
from openai import OpenAI
from pydantic import BaseModel, Field
from rag_vector_store import RAGManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define Pydantic models for test steps
class Step(BaseModel):
    action: Literal["click", "text-enter", "key_enter", "scroll", "error", "finish"]
    element_id: str
    text: str
    component_name: str
    description: str

class TestSteps(BaseModel):
    test_steps: List[Step]

class MarkdownFile(BaseModel):
    markdown_description: str
    content: str
    explanation: Optional[str] = None

class RAGTestingAgent:
    def __init__(self, instruction_folder: str, markdown_folder: str, api_key: str):
        """
        Initialize the RAG-enhanced testing agent.
        
        Args:
            instruction_folder: Path to the folder containing test instruction markdown files
            markdown_folder: Path to the folder containing HTML markdown representation JSON files
            api_key: OpenAI API key
        """
        self.instruction_folder = Path(instruction_folder)
        self.markdown_folder = Path(markdown_folder)
        self.client = OpenAI(api_key=api_key)
        
        # Validate folders exist
        if not self.instruction_folder.exists() or not self.instruction_folder.is_dir():
            raise ValueError(f"Instruction folder {instruction_folder} does not exist or is not a directory")
        
        if not self.markdown_folder.exists() or not self.markdown_folder.is_dir():
            raise ValueError(f"Markdown folder {markdown_folder} does not exist or is not a directory")
        
        # Initialize RAG manager
        self.rag_manager = RAGManager(
            client=self.client,
            instruction_folder=self.instruction_folder,
            markdown_folder=self.markdown_folder
        )
        
        # Index files
        self.rag_manager.index_instructions()
        self.rag_manager.index_markdown_files()
        
        logger.info("RAG Testing Agent initialized and indexed files")

    def parse_instructions(self, instruction_file_path: str) -> List[str]:
        """
        Parse the instruction file into individual steps.
        
        Args:
            instruction_file_path: Path to the instruction file
            
        Returns:
            List of instruction steps
        """
        with open(instruction_file_path, 'r') as f:
            content = f.read()
        
        # Split by lines starting with #
        steps = re.findall(r'#(.*?)(?=\n#|\n$|$)', content, re.DOTALL)
        steps = [step.strip() for step in steps if step.strip()]
        
        logger.info(f"Parsed {len(steps)} steps from {instruction_file_path}")
        return steps

    def load_markdown_from_metadata(self, metadata: Dict[str, Any]) -> Optional[MarkdownFile]:
        """
        Load a markdown file from metadata returned by RAG.
        
        Args:
            metadata: Metadata dictionary from RAG search results
            
        Returns:
            Parsed markdown file
        """
        try:
            return MarkdownFile(
                markdown_description=metadata.get('description', ''),
                content=metadata.get('content', ''),
                explanation=metadata.get('explanation', '')
            )
        except Exception as e:
            logger.error(f"Error loading markdown from metadata: {e}")
            return None

    def generate_test_steps(self, instruction: str, relevant_markdowns: Dict[str, MarkdownFile]) -> TestSteps:
        """
        Generate test steps for a given instruction using the AI model.
        
        Args:
            instruction: Single instruction step
            relevant_markdowns: Dictionary of component names to their markdown representation
            
        Returns:
            Parsed test steps
        """
        # Prepare system prompt
        system_prompt = """You are an AI assistant that generates automated test steps for web applications. 
        Given an instruction and HTML representations, generate a sequence of Selenium-compatible test steps.
        Your output should be in JSON format following the TestSteps schema where each step has:
        - action: the type of action ("click", "text-enter", "key_enter", "scroll", "error", "finish")
        - element_id: the HTML ID of the element to interact with
        - text: any text to enter (for text-enter actions)
        - component_name: the component being interacted with
        - description: a concise description of the step

        Be precise with element_id selection based on the HTML content provided.
        """
        
        # Prepare user message with instruction and available HTML
        user_message = f"Instruction: {instruction}\n\nAvailable HTML representations:\n"
        
        for component_name, markdown in relevant_markdowns.items():
            user_message += f"\nComponent: {component_name}\n"
            user_message += f"Description: {markdown.markdown_description}\n"
            user_message += f"HTML Content: {markdown.content}\n"
            if markdown.explanation:
                user_message += f"Element Explanations: {markdown.explanation}\n"
        
        user_message += "\nGenerate the test steps in JSON format that fulfill this instruction."
        
        try:
            # Call the OpenAI API
            response = self.client.chat.completions.create(
                model="o4-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            
            # Parse the response
            response_content = response.choices[0].message.content
            response_json = json.loads(response_content)
            
            # Validate using Pydantic
            test_steps = TestSteps(**response_json)
            logger.info(f"Generated {len(test_steps.test_steps)} test steps for instruction: '{instruction}'")
            return test_steps
            
        except Exception as e:
            logger.error(f"Error generating test steps: {e}")
            # Return an error step
            return TestSteps(test_steps=[
                Step(
                    action="error",
                    element_id="",
                    text="",
                    component_name="",
                    description=f"Failed to generate test steps: {str(e)}"
                )
            ])

    def process_task(self, task_description: str) -> List[TestSteps]:
        """
        Process a testing task from natural language description to test steps.
        
        Args:
            task_description: Natural language description of the task to perform
            
        Returns:
            List of test steps for each instruction
        """
        # Find the most relevant instruction file using RAG
        instruction_metadata = self.rag_manager.find_instruction_file(task_description)
        
        if not instruction_metadata:
            return [TestSteps(test_steps=[
                Step(
                    action="error",
                    element_id="",
                    text="",
                    component_name="",
                    description=f"No relevant instruction file found for task: {task_description}"
                )
            ])]
        
        # Parse instructions
        instruction_file_path = instruction_metadata['file_path']
        instructions = self.parse_instructions(instruction_file_path)
        
        # Process each instruction
        all_test_steps = []
        for instruction in instructions:
            # Find relevant components using RAG
            relevant_component_metadata = self.rag_manager.find_relevant_components(instruction)
            
            # Load relevant markdown files
            relevant_markdowns = {}
            for component_metadata in relevant_component_metadata:
                component_name = component_metadata['file_name']
                markdown = self.load_markdown_from_metadata(component_metadata)
                if markdown:
                    relevant_markdowns[component_name] = markdown
            
            # Generate test steps
            test_steps = self.generate_test_steps(instruction, relevant_markdowns)
            all_test_steps.append(test_steps)
        
        return all_test_steps

    def execute_test(self, task_description: str) -> List[Dict[str, Any]]:
        """
        Execute a test based on the task description.
        
        This method processes the task and returns the full test plan.
        Integration with Selenium would happen here in a full implementation.
        
        Args:
            task_description: Natural language description of the test to run
            
        Returns:
            List of test steps ready for execution
        """
        test_steps_list = self.process_task(task_description)
        
        # Format for output
        execution_plan = []
        for step_group in test_steps_list:
            execution_plan.append({
                "test_steps": [step.model_dump() for step in step_group.test_steps]
            })
        
        logger.info(f"Test execution plan generated with {len(execution_plan)} step groups")
        return execution_plan


def main():
    """Main entry point for the application."""
    import argparse
    
    parser = argparse.ArgumentParser(description='RAG-Enhanced Web Testing Agent')
    parser.add_argument('--task', required=True, help='Natural language description of the task to test')
    parser.add_argument('--instruction_folder', default='instructions', help='Folder containing instruction markdown files')
    parser.add_argument('--markdown_folder', default='markdown', help='Folder containing HTML markdown representation files')
    parser.add_argument('--api_key', required=True, help='OpenAI API key')
    parser.add_argument('--output', default='test_plan.json', help='Output file for the test plan')
    
    args = parser.parse_args()
    
    try:
        # Initialize the agent
        agent = RAGTestingAgent(
            instruction_folder=args.instruction_folder,
            markdown_folder=args.markdown_folder,
            api_key=args.api_key
        )
        
        # Process the task
        test_plan = agent.execute_test(args.task)
        
        # Save the test plan
        with open(args.output, 'w') as f:
            json.dump(test_plan, f, indent=2)
            
        logger.info(f"Test plan saved to {args.output}")
        
        # Print summary
        print(f"Generated test plan with {sum(len(step_group['test_steps']) for step_group in test_plan)} total steps")
        print(f"Test plan saved to {args.output}")
        
    except Exception as e:
        logger.error(f"Error executing test: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    main()