# ReAct mode additions for SubjectApp.
# Add these to the existing SubjectApp class manually or merge.
# 1. In __init__, add: self.react_mode = False
# 2. Replace get_max_tool_loops:
#    def get_max_tool_loops(self):
#        return 15 if self.react_mode else 3
# 3. Modify get_question_prompt:
#    def get_question_prompt(self):
#        if self.react_mode:
#            prompt_lines = self.config.get("agent_prompt_lines")
#            if prompt_lines:
#                base_prompt = "\\n".join(prompt_lines)
#                tool_instructions = self.get_tool_instructions()
#                return base_prompt + "\\n\\n" + tool_instructions if tool_instructions else base_prompt
#        base_prompt = "\\n".join(self.config.get("question_prompt_lines", []))
#        tool_instructions = self.get_tool_instructions()
#        return base_prompt + "\\n\\n" + tool_instructions if tool_instructions else base_prompt
