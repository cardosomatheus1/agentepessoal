"""A message sent to a subordinate agent right as it finished goes up to its superior.

Messages typed while the agent works become "interventions", read only between steps.
If the subordinate ends first, the message would sit unread on it; hand it upward.
"""

from agent import LoopData
from helpers.extension import Extension


class RepassarMensagem(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        agent = self.agent
        if not agent or agent.number == 0 or agent.intervention is None:
            return
        superior = agent.data.get("_superior")
        if superior is not None and superior.intervention is None:
            superior.intervention, agent.intervention = agent.intervention, None
