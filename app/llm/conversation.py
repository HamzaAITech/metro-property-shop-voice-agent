import uuid

from anthropic import Anthropic

from app.config import settings
from app.llm.prompts import END_CALL_TOOL, SAVE_LEAD_TOOL, build_system_prompt
from app.storage import leads

MODEL = "claude-haiku-4-5-20251001"
TOOLS = [SAVE_LEAD_TOOL, END_CALL_TOOL]
# Safety cap against a runaway tool-call chain - normal turns resolve in 1-2 rounds.
MAX_TOOL_ROUNDS = 5


class Conversation:
    """Holds message history for a single call and drives one LLM turn at a time."""

    def __init__(self, known_phone_number: str = None, is_outbound: bool = False):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.history: list[dict] = []
        self.captured_lead: dict | None = None
        self.should_end_call = False
        self.call_id = str(uuid.uuid4())
        # Set by pipeline.handle_turn after each turn's STT - lets the NEXT
        # turn's filler phrase match the caller's language before we've
        # transcribed anything new yet. Starts "en" since greetings are English.
        self.last_lang = "en"
        # Outbound: the number we dialed. Inbound: caller ID. Lets the system
        # prompt tell the model not to ask for a number it already has.
        self.system_prompt = build_system_prompt(known_phone_number, is_outbound)

    def respond(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        return self._get_reply(collected_text=[])

    def _get_reply(self, collected_text: list, round_num: int = 0) -> str:
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=self.system_prompt,
            tools=TOOLS,
            messages=self.history,
        )

        if response.stop_reason == "max_tokens":
            # A tool_use block can be mid-generation (its JSON input
            # incomplete) when the token limit hits - stop_reason is
            # "max_tokens" here, NOT "tool_use", even if a tool_use block is
            # present. Appending a half-formed tool_use to history with no
            # tool_result would corrupt every future turn (Anthropic's API
            # then rejects the whole conversation). So: keep only completed
            # text, drop any truncated tool_use block entirely.
            text_only_content = [b for b in response.content if b.type == "text"]
            self.history.append({"role": "assistant", "content": text_only_content})
            text_piece = self._extract_text(response)
            if text_piece:
                collected_text.append(text_piece)
            return " ".join(collected_text).strip()

        self.history.append({"role": "assistant", "content": response.content})

        # A response can contain text AND a tool_use together (stop_reason is
        # still "tool_use" in that case) - collect text from EVERY round, not
        # just the final one, or a reply said alongside a tool call gets
        # silently discarded and the caller hears nothing that turn.
        text_piece = self._extract_text(response)
        if text_piece:
            collected_text.append(text_piece)

        if response.stop_reason != "tool_use":
            return " ".join(collected_text).strip()

        if round_num >= MAX_TOOL_ROUNDS:
            # Bail out rather than loop forever - the caller still gets SOME
            # reply instead of the call silently going dead.
            collected_text.append("Sorry, I'm having trouble with that. Could you say it again?")
            return " ".join(collected_text).strip()

        # Claude can chain multiple rounds of tool calls before it actually
        # speaks (e.g. call end_call, then in the very next response also
        # call save_lead). Every tool_use block MUST get a matching
        # tool_result or the next API call fails, so this resolves ALL of
        # them, then recurses - it does not assume this is the last round.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "save_lead":
                self.captured_lead = block.input
                leads.save_lead(self.call_id, block.input)
                result_text = "Lead noted."
            elif block.name == "end_call":
                self.should_end_call = True
                result_text = "Call end noted."
            else:
                result_text = "Unknown tool."
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            )

        self.history.append({"role": "user", "content": tool_results})
        return self._get_reply(collected_text=collected_text, round_num=round_num + 1)

    @staticmethod
    def _extract_text(response) -> str:
        return " ".join(block.text for block in response.content if block.type == "text").strip()
