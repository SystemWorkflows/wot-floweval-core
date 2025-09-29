from __future__ import annotations
import copy
import json
import ast
import copy
import traceback
from typing import Any, Tuple
from src.helpers import flatten
import re
from abc import ABC, abstractmethod
from src.errors import *
from src.thingDescriptionCollection import ThingDescriptionCollection


class NodeFactory:
    @staticmethod
    def produceNode(name:str, parameters:Tuple[Any]):
        match name:
            case "system-action-node":              return SystemActionNode(*parameters)
            case "system-property-node":            return SystemPropertyNode(*parameters)
            case "system-event-node-serv":          return SystemEventServerNode(*parameters)
            case "system-action-node-serv-out":     return SystemActionServerOutNode(*parameters)
            case "system-property-node-serv-out":   return SystemPropertyServerOutNode(*parameters)
            case "change":                          return ChangeNode(*parameters)
            case "switch":                          return SwitchNode(*parameters)
            case _:                                 return PassThroughNode(*parameters)

    @staticmethod
    def produceTriggerNode(name:str, parameters:Tuple[Any]):
        match name:
            case "system-event-node":           return SystemEventNode(*parameters)
            case "system-action-node-serv":     return SystemActionServerNode(*parameters)
            case "system-property-node-serv":   return SystemPropertyServerNode(*parameters)
            case _:                             return None

class Node:
    node = None
    state = {}
    children = []

    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection):
        if not isinstance(tds, ThingDescriptionCollection):
            raise TypeError(f"tds must be a ThingDescriptionCollection instance, got {type(tds).__name__}")
        self.node = node
        self.flow = flow
        self.tds = tds
        self.state = {}
        self.conditions: list[dict] = []
        self.interactions: list[Node] = []
        self.children: list[Node] = []
        self.errors: dict[str, list[str]] = { self.node["id"] : [] }
        self.triggerNode: Node = None

    def addChild(self, child: Node) -> None:
        self.children.append(child)

    def addChildren(self):
        for nodeID in flatten(self.node["wires"]):
            state, conditions= copy.deepcopy((self.state, self.conditions))
            interactions = copy.copy(self.interactions)
            if nodeID not in self.flow:
                self.errors[self.node["id"]].append("Cannot connect to node with id: " + str(nodeID) +". Node not found in flow.")
                continue
            receiverType = self.flow[nodeID]["type"]
            if nodeID in [c.node["id"] for c in interactions]:
                self.errors[self.node["id"]].append("Cannot connect to node with id: " + str(nodeID) +". Loop detected.")
                continue
            if receiverType == "system-event-node":
                self.errors[self.node["id"]].append("Cannot connect to system event node with id: " + str(nodeID))
                continue
            child = NodeFactory.produceNode(receiverType, (self.flow[nodeID], self.flow, self.tds, state, conditions, interactions, self.triggerNode))

            self.addChild(child)
            self.errors = self.errors | child.getErrors()

    def getChildren(self):
        children = copy.copy(self.children)
        for child in self.children:
            children += child.getChildren()

        return children

    def getErrors(self):
        return self.errors
    
    @abstractmethod
    def match(self, subflow_matches):
        return []
    
    def extractConditions(self):
        conditions = []

        for child in self.children:
            conditions += child.extractConditions()

        return conditions

#%% Secondary Nodes
class SecondaryNode(Node):

    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection, incomingState: dict, incomingConditions: list[dict] = [], previousInteractions: list[Node] = [], triggerNode: Node = None):
        super().__init__(node, flow, tds)
        self.incomingState = incomingState
        self.state = copy.deepcopy(incomingState)
        self.incomingConditions = incomingConditions
        self.conditions = copy.deepcopy(incomingConditions)
        self.previousInteractions = previousInteractions
        self.interactions = copy.deepcopy(previousInteractions)
        self.triggerNode = triggerNode

    # def stateLookup(self,path):
    #     search = path.split(".")

    #     if search[0] == "msg":
    #         search = search[1:]

    #     data = copy.deepcopy(self.state)

    #     for j in search:
    #         data = data[j]
    #         if data["type"] == "object":
    #             data = data["properties"]

    #     return data

class PassThroughNode(SecondaryNode):
    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection, incomingState: dict, incomingConditions: list[dict] = [], previousInteractions: list[Node] = [], triggerNode: Node = None):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions, triggerNode)
        self.state = self.incomingState
        self.addChildren()

class SwitchNode(SecondaryNode):
    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection, incomingState: dict, incomingConditions: list[dict] = [], previousInteractions: list[Node] = [], triggerNode: Node = None):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions, triggerNode)
        self.updateConditions()
        self.addChildren()

    def updateConditions(self):
        def stateLookup(path):
            search = path.split(".")

            if search[0] == "msg":
                search = search[1:]

            data = copy.deepcopy(self.incomingState)
            for j in search:
                data = data[j]
                if data["type"] == "object":
                    data = data["properties"]

            return data

        rules = self.node["rules"]

        try:
            property = stateLookup(self.node["property"])
        except Exception as e:
            self.errors[self.node["id"]].append("Error in switch node: could not find property in Node-Red msg.")
            print("Error in switch node: ", e)
            print(traceback.format_exc())
            property = {}

        for rule in rules:
            rule["property"] = property

    def addChildren(self):
        if len(self.node["wires"]) != len(self.node["rules"]):
            self.errors[self.node["id"]].append("Number of rules does not match number of outputs in switch node.")
            return
        
        for nodeIndex in range(0, len(self.node["wires"])):
            for connectedNode in self.node["wires"][nodeIndex]:
                if connectedNode not in self.flow:
                    self.errors[self.node["id"]].append("Cannot connect to node with id: " + str(connectedNode) +". Node not found in flow.")
                    continue
                connectedNodeType = self.flow[connectedNode]["type"]

                state, conditions, interactions = copy.deepcopy((
                    self.state,
                    self.incomingConditions + [self.node["rules"][nodeIndex]],
                    self.interactions
                ))

                child = NodeFactory.produceNode(connectedNodeType, (self.flow[connectedNode], self.flow, self.tds, state, conditions, interactions, self.triggerNode))

                self.addChild(child)
                self.errors = self.errors | child.getErrors()

class ChangeNode(SecondaryNode):
    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection, incomingState: dict, incomingConditions: list[dict] = [], previousInteractions: list[Node] = [], triggerNode: Node = None):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions, triggerNode)
        self.updateState()
        self.addChildren()
    
    def updateState(self):

        def stateLookup(path):
            search = path.split(".")
            
            if search[0] == "msg":
                search = search[1:]

            data = copy.deepcopy(self.state) # Changed from incomingState to allow changes from previous rules to be reflected
            try:
                for j in search[:-1]:
                    data = data[j]

                    if data["type"] == "object":
                        data = data["properties"]
                
                data = data[search[-1]]
                return data
            except Exception as e:
                self.errors[self.node["id"]].append("Error in state lookup in change node with id: " + str(self.node["id"]) + ". Could not find path (" + path + ") from provided rules in change node with  data state: " + json.dumps(self.state))
                raise e

        def objectHandler(object):
            x = object[1:-1]
            x = x.replace(" ", "")
            regex = r'({[^{}]*})|("[^"]*")|,'
            parts = []
            last_index = 0
            for match in re.finditer(regex, x):
                if match.group(0) == ',':
                    parts.append(x[last_index:match.start()].strip())
                    last_index = match.end()
                # Add the last part of the string
            parts.append(x[last_index:].strip())

            output = {}
            for part in parts:
                part = part.split(":", 1)
                typ = self.__check_type(part[1])
                set_state(typ, output, part[0][1:-1], part[1], source)
            return {"type": "object", "properties": output}

        def set_state(typ, state_target, state_name, lookupTarget, source):
            if typ == "lookUp":
                state_target[state_name] = stateLookup(lookupTarget)
            elif typ == int:
                state_target[state_name] = {"type": "integer", "source": source}
            elif typ == float:
                state_target[state_name] = {"type": "number", "source": source}
            elif typ == str:
                state_target[state_name] = {"type": "string", "source": source}
            elif typ == bool:
                state_target[state_name] = {"type": "boolean", "source": source}
            elif typ == 'typeError':
                state_target[state_name] = {"type": "string", "source": source}
            elif typ == "object":
                state_target[state_name] = objectHandler(lookupTarget)
            elif typ == 'equation':
                equation = lookupTarget.replace(" ", "")
                parts = None
                if "+" in equation:
                    parts = equation.split("+")
                    op = "add"
                elif "-" in equation:
                    parts = equation.split("-")
                    op = "sub"
                elif "*" in equation:
                    parts = equation.split("*")
                    op = "mul"
                elif "/" in equation:
                    parts = equation.split("/")
                    op = "div"
                if parts == None or len(parts) != 2:
                    raise Exception("Invalid equation in change node: " + lookupTarget)
                for part in parts:
                    typ = self.__check_type(part)
                    if typ == "lookUp":
                        state_target[state_name] = stateLookup(part)
                        break
                state_target[state_name]["operation"] = op
                state_target[state_name]["operands"] = parts

            else:
                self.errors[self.node["id"]].append("could not handle jsonata data type in change node rule")
                raise Exception("jsonata data could not be handled")

        for rule in self.node["rules"]:
            source = {"type": "change", "id": self.node["id"]}

            try:
                if rule["t"] == "set":
                    if rule["tot"] == "jsonata":
                        if rule["to"][0] == "{": # jsonata
                            self.state[rule["p"]] = objectHandler(rule["to"])
                        else:
                            typ = self.__check_type(rule["to"])
                            set_state(typ, self.state, rule["p"], rule["to"], source)

                    elif rule["tot"] == "msg": # Check this
                        lu = stateLookup(rule["to"])
                        p = rule["p"].split(".")
                        data = self.state

                        for j in p[:-1]:
                            data = data[j]

                            if data["type"] == "object":
                                data = data["properties"]

                        data[p[-1]] = lu

                    elif rule["tot"] == "str":
                        self.state[rule["p"]] = {"type": "string", "source": source}

                    elif rule["tot"] == "num":
                        self.state[rule["p"]] = {"type": "number", "source": source}

                    elif rule["tot"] == "bool":
                        self.state[rule["p"]] = {"type": "boolean", "source": source}

                    elif rule["tot"] == "json":
                        properties = {}
                        self.state[rule["p"]] = {"type": "object"}

                        for k, v in json.loads(rule["to"]).items():
                            typ = type(v)
                            set_state(typ, properties, k, None, source)

                        self.state[rule["p"]]["properties"] = properties
                elif rule["t"] == "delete":
                    path = rule["p"].split(".")
                    state = self.state
                    for j in path[:-1]:
                        if j not in state:
                            raise Exception("Invalid path in delete rule: " + rule["p"])
                        state = state[j]["properties"]
                    del state[path[-1]]
                else:
                    self.errors[self.node["id"]].append("Invalid t value in change node. Expected set or delete, got: " + rule["t"])
                    raise Exception("Invalid t value in change node. Expected set or delete, got: " + rule["t"])
            except Exception as e:
                print("Error in change node: ", e)
                print(traceback.format_exc())

    def __check_type(self, value):

        if (type(value)== str) and (value.startswith("{")):
            return "object"
        
        if (type(value)== str) and (value.startswith('msg.') or ('payload.' in value and not value.startswith('"'))) and "&" not in value:
            if "+" in value or "-" in value or "*" in value or "/" in value:
                return 'equation'
            return 'lookUp'
        
        try:
            evaluated_value = ast.literal_eval(value)
            return type(evaluated_value)
        except (ValueError, SyntaxError):
            return 'typeError'

class InteractionNode(SecondaryNode):
    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection, incomingState: dict, incomingConditions: list[dict] = [], previousInteractions: list[Node] = [], triggerNode: Node = None):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions, triggerNode)
        self.validatePayload()
        self.updateState()
        self.interactions.append(self)
        self.addChildren()

    def updateState(self):
        pass

    def validatePayload(self):
        pass

    def _validatePayload(self, expectedInput: dict):
        payload = copy.deepcopy(self.incomingState["payload"])

        if payload == {} and expectedInput == {}:
            return True

        if (payload == {} and expectedInput != {}) or (payload != {} and expectedInput == {}):
            return False
        
        if payload["type"] != "object":
            if payload["type"] != expectedInput["type"]:
                self.errors[self.node["id"]].append("Error with input! Expected: " + json.dumps(expectedInput) + ". Got: " + json.dumps(payload) + ".")
                return False

            return True
        
        incProp = {}
        for propertyName, propertyValue in payload["properties"].items():
            if "type" in propertyValue:
                incProp[propertyName] = propertyValue["type"]
            else:
                incProp[propertyName] = None

        actInProp = {}
        for propertyName, propertyValue in expectedInput["properties"].items():
            if "type" in propertyValue:
                actInProp[propertyName] = propertyValue["type"]
            else:
                actInProp[propertyName] = None

        if sorted(incProp) != sorted(actInProp):
            self.errors[self.node["id"]].append("Error with input! Expected: " + json.dumps(expectedInput) + ". Got: " + json.dumps(payload) + ".")
            return False

        return True

    def conditionsMatch(self, conditions: list[dict]):
        for condition in conditions:
            if ("property" not in condition) or ("source" not in condition["property"]):
                    continue

            if "id" in condition["property"]["source"]:
                del condition["property"]["source"]["id"] # Remove id from source

            if "prev" in condition["property"]["source"]:
                del condition["property"]["source"]["prev"] # Remove prev from source

        for condition in self.conditions:
            if ("property" not in condition) or ("source" not in condition["property"]):
                continue

            if "id" in condition["property"]["source"]:
                del condition["property"]["source"]["id"] # Remove id from source
            
            if "prev" in condition["property"]["source"]:
                del condition["property"]["source"]["prev"] # Remove prev from source

        if conditions == self.conditions:
            return True
        
        return False
    
    def preConditionsMatch(self, pre_nodes: list[str]):
        if pre_nodes == []:
            return True
        
        prev = []
        for i in self.previousInteractions: # Add filtering to exclude irrelevant interactions when selecting which interactions to check
            if i.node["type"] == "system-action-node":
                prev.append(i.node["thingAction"])
            elif (i.node["type"] == "system-property-node") and (i.node["mode"] == "write"):
                prev.append(i.node["thingProperty"])

        if pre_nodes != prev:
            return False
        
        return True

    def inputMatch(self, required_input: dict):
        if not self.validatePayload():
            return False

        if (required_input["type"] != "object") and (self.incomingState["payload"]["type"] != "object"):
            if "source" not in required_input:
                return True

            required_source = required_input["source"]
            incoming_source = self.incomingState["payload"]["source"]

            if required_source["type"] != incoming_source["type"]:
                return False

            if required_source["type"] == "event":
                return True

            if "name" not in required_source:
                return True

            if required_source["name"] != incoming_source["name"]:
                return False

            if "pos" not in required_source:
                return True

            if required_source["pos"]["location"] == "last":
                node = required_source["pos"]["node"]
                x = self.previousInteractions[len(incoming_source["prev"]) + 1:]
                return node not in x

            if required_source["pos"]["location"] == "after":
                node = required_source["pos"]["node"]
                return node in incoming_source["prev"]

        elif (required_input["type"] == "object") and (self.incomingState["payload"]["type"] == "object"):
            for required_input_property_name, required_input_property_value in required_input["properties"].items():
                if required_input_property_name not in self.incomingState["payload"]["properties"]:
                    return False

                if "source" not in required_input_property_value:
                    return True

                required_source = required_input_property_value["source"]
                incoming_source = self.incomingState["payload"]["properties"][required_input_property_name]["source"]

                if required_source["type"] != incoming_source["type"]:
                    return False

                if required_source["type"] == "event":
                    return True

                if "name" not in required_source:
                    return True

                if required_source["name"] != incoming_source["name"]:
                    return True

                if "pos" not in required_source:
                    return True

                if required_source["pos"] != "last": # Finish this
                    return False

                for interaction in reversed(self.previousInteractions):
                    name = None

                    if interaction.node["type"] == "system-action-node":
                        name = interaction.node["thingAction"]

                    elif interaction.node["type"] == "system-property-node":
                        name = interaction.node["thingProperty"]

                    if name != required_input["name"]:
                        continue

                    if incoming_source["id"] == interaction.node["id"]:
                        return True
        
        return False
    
    def thingMatch(self, thingID: str) -> bool:
        pass


    def match(self, candidates: list, subflow_matches: list):
        match = {
            "thingMatch": False,
            "preConditionMatch": False, 
            "conditionsMatch": False, 
            "inputMatch": False
        }

        if "thingID" in candidates[0][1]:
            candidates = [cand for cand in candidates if self.thingMatch(cand[1]["thingID"])]

            if len(candidates) > 0:
                match["thingMatch"] = True

        else:
            match["thingMatch"] = True

        candidates = [cand for cand in candidates if self.preConditionsMatch(cand[1]["pre_nodes"])]

        if len(candidates) > 0:
            match["preConditionMatch"] = True
        
        candidates = [cand for cand in candidates if self.conditionsMatch(cand[1]["conditions"])]

        if len(candidates) > 0:
            match["conditionsMatch"] = True
        
        candidates = [cand for cand in candidates if self.inputMatch(cand[1]["input"])]

        if len(candidates) > 0:
            match["inputMatch"] = True
    
        # Should be no more than one candidate but just in case checks list, 
        # this check prevents multiple nodes matching against the same case.
        for candidate in candidates:
            subflow_matches.remove(candidate)

        status = match["preConditionMatch"] and match["conditionsMatch"] and match["inputMatch"]

        return {
            "status": status, 
            "name": self.node["thingAction"], 
            "match": match, 
            "candidates": candidates
        }
    
    def _extractConditions(self):
        input = self.incomingState["payload"]

        if "properties" in input: # Removes the id as it is unnecesary
            for i in input["properties"].values():
                if "source" not in i:
                    continue

                if "id" in i["source"]:
                    del i["source"]["id"]

                if "prev" in i["source"]:
                    del i["source"]["prev"]

        pre_nodes = []
        
        for interaction in self.previousInteractions:
            if interaction.node["type"] == "system-action-node":
                prev = interaction.node["thingAction"]
                pre_nodes.append(prev)

            elif (interaction.node["type"] == "system-property-node") and (interaction.node["mode"] == "write"):
                prev = interaction.node["thingProperty"]
                pre_nodes.append(prev)

        c = {"pre_nodes": pre_nodes, "conditions": self.conditions, "input": input}

        return c
    
    def getThingIDFromThingNode(self, thingNodeID: str):
        if thingNodeID not in self.flow:
            self.errors[self.node["id"]].append("Cannot find thing node with id: " + str(thingNodeID))
            return None
        
        thingNode = self.flow[thingNodeID]

        if "TD" not in thingNode:
            self.errors[self.node["id"]].append(f"Thing node with id: {thingNodeID} does not have a thing.")
            return None
        
        return json.loads(thingNode["TD"])["id"]


#%% System-Nodes
class SystemActionNode(InteractionNode):

    def thingMatch(self, thingID: str) -> bool:
        return self.node["thingID"] == thingID

    def extractConditions(self):
        conditions = super().extractConditions()
        c = self._extractConditions()
        if "thingID" in self.node:
            c["thingID"] = self.node["thingID"]
        conditions.append([self.node["thingAction"], c])
        return conditions

    def validatePayload(self):
        expectedInput = self.tds.getActionInput(self.node["thingAction"])
        return super()._validatePayload(expectedInput)

    def updateState(self):
        if not self.node["outputToMsg"]:
            self.state = self.incomingState
            return
        
        output = self.tds.getActionOutput(self.node["thingAction"])

        if output == None:
            self.state["payload"] = {}
            return
        
        prev = []
        for interaction in self.previousInteractions:
            if interaction.node["type"] == "system-action-node":
                prev.append(interaction.node["thingAction"])
            if (interaction.node["type"] == "system-property-node") and (interaction.node["mode"] == "write"):
                prev.append(interaction.node["thingProperty"])
                    
        source = {"type":"action", "name": self.node["thingAction"], "id": self.node["id"], "prev": prev} # Replace id with generic counter

        if output["type"] != "object":
            output["source"] = source
        else:
            for property in output["properties"].values():
                property["source"] = source

        self.state["payload"] = output

    def match(self, subflow_matches: list):
        candidates = []
        for subflow_match in subflow_matches:
            if subflow_match[0] == self.node["thingAction"]:
                candidates.append(subflow_match)

        return super().match(candidates, subflow_matches)


class SystemPropertyNode(InteractionNode):

    def thingMatch(self, thingID: str) -> bool:
        return self.node["thingID"] == thingID

    def extractConditions(self):
        conditions = super().extractConditions()
        c = self._extractConditions()
        if "thingID" in self.node:
            c["thingID"] = self.node["thingID"]
        conditions.append([self.node["thingProperty"], c])
        return conditions

    def updateState(self):
        if self.node["mode"] != "read":
            self.state = self.incomingState
            return
        
        output = self.tds.getPropertyValue(self.node["thingProperty"])
        prev = []

        for interaction in self.previousInteractions:
            if interaction.node["type"] == "system-action-node":
                prev.append(interaction.node["thingAction"])
            if (interaction.node["type"] == "system-property-node") and (interaction.node["mode"] == "write"):
                prev.append(interaction.node["thingProperty"])

        source = {"type":"property", "name": self.node["thingProperty"], "id": self.node["id"], "prev": prev}

        if output["type"] != "object":
            output["source"] = source
        else:
            for property in output["properties"].values():
                property["source"] = source

        self.state["payload"] = output

    def validatePayload(self):
        if self.node["mode"] != "write":
            return True
    
        propertyInput = self.tds.getPropertyValue(self.node["thingProperty"])
        return super()._validatePayload(propertyInput)

    def match(self, subflow_matches: list):
        candidates = []

        for subflow_match in subflow_matches:
            if subflow_match[0] == self.node["thingProperty"]:
                candidates.append(subflow_match)

        return super().match(candidates, subflow_matches)

class SystemEventServerNode(InteractionNode):

    def thingMatch(self, thingID: str) -> bool:
        return self.getThingIDFromThingNode(self.node["thing"]) == thingID

    def extractConditions(self):
        conditions = super().extractConditions()
        c = self._extractConditions()
        c["thingID"] = self.getThingIDFromThingNode(self.node["thing"])
        conditions.append([self.node["eventName"], c])
        return conditions

    def validatePayload(self):
        eventData = self.tds.getEventData(self.node["eventName"])
        return super()._validatePayload(eventData)
    
    def match(self, subflow_matches: list):
        candidates = []

        for subflow_match in subflow_matches:
            if subflow_match[0] == self.node["eventName"]:
                candidates.append(subflow_match)

        return super().match(candidates, subflow_matches)
    
class SystemPropertyServerOutNode(InteractionNode):

    def thingMatch(self, thingID: str) -> bool:
        return self.getThingIDFromThingNode(self.node["thing"]) == thingID

    def extractConditions(self):
        conditions = super().extractConditions()
        c = self._extractConditions()
        c["thingID"] = self.getThingIDFromThingNode(self.triggerNode.node["thing"])
        conditions.append([self.triggerNode.node["propertyName"]+"-out", c])
        return conditions

    def validatePayload(self):
        propertyValue = self.tds.getPropertyValue(self.triggerNode.node["propertyName"])
        return super()._validatePayload(propertyValue)

    def match(self, subflow_matches: list):
        candidates = []

        for subflow_match in subflow_matches:
            if subflow_match[0] == self.node["propertyName"]:
                candidates.append(subflow_match)

        return super().match(candidates, subflow_matches)

class SystemActionServerOutNode(InteractionNode):

    def thingMatch(self, thingID: str) -> bool:
        return self.getThingIDFromThingNode(self.node["thing"]) == thingID

    def extractConditions(self):
        conditions = super().extractConditions()
        c = self._extractConditions()
        c["thingID"] = self.getThingIDFromThingNode(self.triggerNode.node["thing"])
        conditions.append([self.triggerNode.node["actionName"]+"-out", c])
        return conditions

    def validatePayload(self):
        actionData = self.tds.getActionOutput(self.triggerNode.node["actionName"])
        return super()._validatePayload(actionData)
    
    def match(self, subflow_matches: list):
        candidates = []

        for subflow_match in subflow_matches:
            if subflow_match[0] == self.node["actionName"]:
                candidates.append(subflow_match)

        return super().match(candidates, subflow_matches)

class TriggerNode(Node):
    def __init__(self, node: dict, flow: dict[str, dict], tds: ThingDescriptionCollection):
        super().__init__(node, flow, tds)
        self.triggerNode = self
        self.extractState()
        self.addChildren()

    def extractState(self):
        pass

    def _child_matchable(self, child: Node):
        if child.node["type"] in ["system-action-node", "system-event-node-serv", "system-property-node-serv-out", "system-action-node-serv-out"] or (child.node["type"] == "system-property-node" and child.node["mode"] == "write"):
            return True
        return False

    def match(self, subflow_matches: list):
        children = self.getChildren()
        matches = {}

        for child in children:
            if not self._child_matchable(child):
                continue
            
            if child.node["id"] not in matches:
                matches[child.node["id"]] = []
            matches[child.node["id"]].append(child.match(subflow_matches))

        left_over = copy.deepcopy(subflow_matches) # Adjust scores for left over cases- e.g. not enough nodes in real flow compared to true flow

        return {"matches": matches, "left_over": left_over}


class SystemEventNode(TriggerNode):
    
    def extractState(self):
        eventData = self.tds.getEventData(self.node["thingEvent"])
        self.state["payload"] = eventData
        if self.state["payload"] is None:
            return
        
        if self.state["payload"]["type"] != "object":
            self.state["payload"]["source"] = {"type":"event", "name": self.node["thingEvent"], "id": self.node["id"]}
        
        for property in self.state["payload"]["properties"].values():
            property["source"] = {"type":"event", "name": self.node["thingEvent"], "id": self.node["id"]}

    
class SystemPropertyServerNode(TriggerNode):

    def extractState(self):
        propertyValue = self.tds.getPropertyValue(self.node["propertyName"])
        self.state["payload"] = propertyValue
        if self.state["payload"] is None:
            return
        
        if self.state["payload"]["type"] != "object":
            self.state["payload"]["source"] = {"type":"system-property-node-serv", "name": self.node["propertyName"], "id": self.node["id"]}
        
        for property in self.state["payload"]["properties"].values():
            property["source"] = {"type":"system-property-node-serv", "name": self.node["propertyName"], "id": self.node["id"]}


class SystemActionServerNode(TriggerNode):

    def extractState(self):
        actionData = self.tds.getActionInput(self.node["actionName"])
        self.state["payload"] = actionData
        if self.state["payload"] is None:
            return
        
        if self.state["payload"]["type"] != "object":
            self.state["payload"]["source"] = {"type":"system-action-node-serv", "name": self.node["actionName"], "id": self.node["id"]}
        
        for property in self.state["payload"]["properties"].values():
            property["source"] = {"type":"system-action-node-serv", "name": self.node["actionName"], "id": self.node["id"]}