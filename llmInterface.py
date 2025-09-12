from google import genai
from google.genai import types
from openai import OpenAI
from typing import Any, Tuple
import time
class llmFactory:
    llmChat = None

    @staticmethod
    def produceChat(name:str, parameters:Tuple[Any]):
        match name:
            case "models/gemini-2.5-flash":             return geminiChat(*parameters)
            case "models/gemini-2.5-pro":               return geminiChat(*parameters)
            case "models/gemini-2.5-flash-lite":        return geminiChat(*parameters)
            case "openai/gpt-oss-120b:free":            return openRouterChat(*parameters)
            case _:                                     return None



class llmChat:
    def __init__(self, parameters):
        pass

    def chat(self, prompt):
        pass

class geminiChat(llmChat):
    def __init__(self, parameters):
        client = genai.Client(api_key="AIzaSyCvx6ffmJxe0XkcApWKDIMi5jrX3W7kQ6U")#no billing connected
        self.chat = client.chats.create(
            model=parameters["model"],
            config=types.GenerateContentConfig(
                temperature=parameters["temperature"],
                #candidate_count=parameters["candidate_count"],
                seed=parameters["seed"],
                max_output_tokens=parameters["max_output_tokens"],
                response_mime_type=parameters["response_mime_type"]
            )
        )

    def send_message(self, prompt):
        time_start = time.time()
        response = self.chat.send_message(prompt)
        time_end = time.time()
        delta_t = time_end - time_start
        resp = None
        try:
            resp = response.candidates[0].content.parts[0].text
            if resp == None:
                raise Exception("failed to generate flow")
        except:
            raise Exception("failed to generate flow")
        
        return {"response": resp, "metadata":{"time": delta_t, "input_tokens": response.usage_metadata.prompt_token_count, "output_tokens": response.usage_metadata.candidates_token_count}}
class openRouterChat(llmChat):
    def __init__(self, parameters):
        self.parameters = parameters
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key="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"#no billing connected
        )


    def send_message(self, prompt):
        completion = self.client.chat.completions.create(
        model=self.parameters.get("model"),
        messages=[
            {
            "role": "user",
            "content": [
                {
                "type": "text",
                "text": prompt
                }
            ]
            }
        ]
        )
        print(completion.choices[0].message.content)