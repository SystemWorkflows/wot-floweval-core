import copy
import json
import ast
import copy
import traceback
from typing import Any, Tuple
from src.helpers import flatten

class NodeFactory:
    @staticmethod
    def produceNode(name:str, parameters:Tuple[Any]):
        match name:
            case "system-action-node":      return SystemActionNode(*parameters)
            case "system-property-node":    return SystemPropertyNode(*parameters)
            case "change":                  return ChangeNode(*parameters)
            case "switch":                  return SwitchNode(*parameters)
            case _:                         return PassThroughNode(*parameters)

class Node:
    node = None
    state = {}
    children = []
    
    def __init__(self, node, flow, tds):
        self.node = node
        self.flow = flow
        self.tds = tds
        self.state = {}
        self.conditions = []
        self.interactions = []
        self.children = []
        self.errors = { self.node["id"] : [] }

    def addChild(self, child):
        self.children.append(child)

    def addChildren(self):
        for nodeID in flatten(self.node["wires"]):
            state, conditions, interactions = copy.deepcopy((self.state, self.conditions, self.interactions))
            receiverType = self.flow[nodeID]["type"]

            child = NodeFactory.produceNode(receiverType, (self.flow[nodeID], self.flow, self.tds, state, conditions, interactions))

            self.addChild(child)
            self.errors = self.errors | child.getErrors()

    def getChildren(self):
        """

        """

        children = copy.deepcopy(self.children)

        for i in self.children:
            children += i.getChildren()

        return children

    def getErrors(self):
        return self.errors
    
    def match(self, subflow_matches):
        return []
    
    def extractConditions(self):
        conditions = []

        for i in self.children:
            conditions += i.extractConditions()

        return conditions

#%% Secondary Nodes
class SecondaryNode(Node):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds)
        self.incomingState = incomingState
        self.state = copy.deepcopy(incomingState)
        self.incomingConditions = incomingConditions
        self.conditions = copy.deepcopy(incomingConditions)
        self.previousInteractions = previousInteractions
        self.interactions = copy.deepcopy(previousInteractions)

class ChangeNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
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
                self.errors[self.node["id"]].append("Error in change node state lookup: " + str(e))
                raise e

        for rule in self.node["rules"]:
            source = {"type": "change", "id": self.node["id"]}

            try:
                if rule["tot"] == "jsonata":
                    if rule["to"][0] == "{": # jsonata
                        x = rule["to"][1:-1]
                        y = x.replace(" ", "")

                        parts = y.split(',"')
                        if len(parts) > 1:
                            for x in range(1,len(parts)):
                                parts[x] = '"' + parts[x]
                        
                        output = {}
                        for part in parts:
                            part = part.split(":", 1)
                            typ = self.__check_type(part[1])

                            if typ == "lookUp":
                                output[part[0][1:-1]] = stateLookup(part[1])
                            elif typ == int:
                                output[part[0][1:-1]] = {"type": "integer", "source": source}
                            elif typ == float:
                                output[part[0][1:-1]] = {"type": "number", "source": source}
                            elif typ == str:
                                output[part[0][1:-1]] = {"type": "string", "source": source}
                            elif typ == bool:
                                output[part[0][1:-1]] = {"type": "boolean", "source": source}
                            elif typ == 'typeError':
                                output[part[0][1:-1]] = {"type": "string", "source": source}
                                
                        self.state[rule["p"]] = {"type": "object"}
                        self.state[rule["p"]]["properties"] = output
                    else:
                        typ = self.__check_type(rule["to"])

                        if typ == "lookUp":
                            self.state[rule["p"]] = stateLookup(rule["to"])
                        elif typ == int:
                            self.state[rule["p"]] = {"type": "integer", "source": source}
                        elif typ == float:
                            self.state[rule["p"]] = {"type": "number", "source": source}
                        elif typ == str:
                            self.state[rule["p"]] = {"type": "string", "source": source}
                        elif typ == bool:
                            self.state[rule["p"]] = {"type": "boolean", "source": source}
                        elif typ == 'typeError':
                            self.state[rule["p"]] = {"type": "string", "source": source}

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
                        typ = self._self.__check_type(v)

                        if typ == int:
                            properties[k] = {"type": "integer", "source": source}
                        elif typ == float:
                            properties[k] = {"type": "number", "source": source}
                        elif typ == str:
                            properties[k] = {"type": "string", "source": source}
                        elif typ == bool:
                            properties[k] = {"type": "boolean", "source": source}   

                    self.state[rule["p"]]["properties"] = properties
            except Exception as e:
                print("Error in change node: ", e)
                print(traceback.format_exc())
    
    def __check_type(self, value):
        if value.startswith('msg.') or ('payload.' in value and not value.startswith('"')):
            return 'lookUp'
        
        try:
            evaluated_value = ast.literal_eval(value)
            return type(evaluated_value)
        except (ValueError, SyntaxError):
            return 'typeError'

class InteractionNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions=[], previousInteractions=[]):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
        self.validatePayload()
        self.updateState()
        self.interactions.append(self)
        self.addChildren()

    def updateState(self):
        pass

    def validatePayload(self):
        pass

class PassThroughNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
        self.state = self.incomingState
        self.addChildren()

class SwitchNode(SecondaryNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)
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
            print("Error in switch node: ", e)
            print(traceback.format_exc())
            property = {}

        for rule in rules:
            rule["property"] = property

    def addChildren(self):
        if len(self.node["wires"]) != len(self.node["rules"]):
            return
        
        for nodeIndex in range(0, len(self.node["wires"])):
            for connectedNode in self.node["wires"][nodeIndex]: 
                connectedNodeType = self.flow[connectedNode]["type"]

                state, conditions, interactions = copy.deepcopy((
                    self.state,
                    self.incomingConditions + [self.node["rules"][nodeIndex]],
                    self.interactions
                ))

                child = NodeFactory.produceNode(connectedNodeType, (self.flow[connectedNode], self.flow, self.tds, state, conditions, interactions))

                self.addChild(child)
                self.errors = self.errors | child.getErrors()

#%% System-Nodes
class SystemActionNode(InteractionNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)

    def extractConditions(self):
        conditions = super().extractConditions()
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

        c = [self.node["thingAction"], {"pre_nodes": pre_nodes, "conditions": self.conditions, "input": input}]
        conditions.append(c)

        return conditions

    def validatePayload(self):
        if self.incomingState["payload"] == {}:
            return False
        
        actionInput = self.tds.getActionInput(self.node["thingAction"])
        payload = copy.deepcopy(self.incomingState["payload"])

        if payload["type"] != "object":
            if payload["type"] != actionInput["type"]:
                self.errors[self.node["id"]].append("expected: " + json.dumps(actionInput) + " got: " + json.dumps(payload))
                return False

            return True
        
        incProp = {}
        for propertyName, propertyValue in payload["properties"].items():
            incProp[propertyName] = propertyValue["type"]

        actInProp = {}
        for propertyName, propertyValue in actionInput["properties"].items():
            actInProp[propertyName] = propertyValue["type"]

        if sorted(incProp) != sorted(actInProp):
            self.errors[self.node["id"]].append("expected: " + json.dumps(actionInput) + " got: " + json.dumps(payload))
            return False

        return True

            
    
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

    def conditionsMatch(self, conditions):
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

    def inputMatch(self, input):
        if not self.validatePayload():
            return False
        
        if (input["type"] != "object") and (self.incomingState["payload"]["type"] != "object"):
            if "source" not in input:
                return True
            
            i_source = input["source"]
            p_source = self.incomingState["payload"]["source"]
            
            if i_source["type"] != p_source["type"]:
                return False
            
            if i_source["type"] == "event":
                return True
            
            if "name" not in i_source:
                return True
            
            if i_source["name"] != p_source["name"]:
                return False
            
            if "pos" not in i_source:
                return True
            
            if i_source["pos"]["location"] == "last":
                node = i_source["pos"]["node"]
                x = self.previousInteractions[len(p_source["prev"]) + 1:]
                return node not in x

            if i_source["pos"]["location"] == "after":
                node = i_source["pos"]["node"]
                return node in p_source["prev"]
            
        elif (input["type"] == "object") and (self.incomingState["payload"]["type"] == "object"):
            for k, v in input["properties"].items():
                if k not in self.incomingState["payload"]["properties"]:
                    return False
                
                if "source" not in v:
                    return True
                
                i_source = v["source"]
                p_source = self.incomingState["payload"]["properties"][k]["source"]

                if i_source["type"] != p_source["type"]: # Does this need a closing else?
                    continue
                
                if i_source["type"] == "event":
                    return True
                
                if "name" not in i_source:
                    return True
                
                if i_source["name"] != p_source["name"]:
                    return True
                
                if "pos" not in i_source:
                    return True
                
                if i_source["pos"] != "last": # Finish this
                    return False
                
                for interacts in reversed(self.previousInteractions):
                    name = None

                    if interacts.node["type"] == "system-action-node":
                        name = interacts.node["thingAction"]

                    if  interacts.node["type"] == "system-property-node":
                        name = interacts.node["thingProperty"]

                    if name != input["name"]:
                        continue
                    
                    if p_source["id"] == interacts.node["id"]:
                        return True
        
        return False


    def preConditionsMatch(self, pre_nodes):
        if pre_nodes == []:
            return True
        
        prev = []
        for i in self.previousInteractions: # Add filtering to exclude irrelevant interactions when selecting which interactions to check
            if i.node["type"] == "system-action-node":
                prev.append(i.node["thingAction"])
            if (i.node["type"] == "system-property-node") and (i.node["mode"] == "write"):
                prev.append(i.node["thingProperty"])

        if pre_nodes != prev:
            return False
        
        return True
    
    def match(self, subflow_matches):
        # print node details for match types
        print("subflow matches: ", subflow_matches)
        
        candidates = []
        for i in subflow_matches:
            if i[0] == self.node["thingAction"]:
                candidates.append(i)
        
        match = {"preConditionMatch": False, "conditionsMatch": False, "inputMatch": False}
        candidates = [x for x in candidates if self.preConditionsMatch(x[1]["pre_nodes"])]

        if candidates != []:
            match["preConditionMatch"] = True
            candidates = [x for x in candidates if self.conditionsMatch(x[1]["conditions"])]

            if candidates != []:
                match["conditionsMatch"] = True
                candidates = [x for x in candidates if self.inputMatch(x[1]["input"])]

                if candidates != []:
                    match["inputMatch"] = True

        for i in candidates: # Should be no more than one candidate but just in case checks list, this check prevents multiple nodes matching against the same case.
            subflow_matches.remove(i)

        status = match["preConditionMatch"] and match["conditionsMatch"] and match["inputMatch"]

        print("final Candidates: " + json.dumps(candidates))
        return {"status": status, "name": self.node["thingAction"], "match": match, "candidates": candidates} # Needs reversing to check flow validity

class SystemEventNode(Node):
    def __init__(self, node, flow, tds):
        super().__init__(node, flow, tds)
        self.extractState()
        self.addChildren()
    
    def extractState(self):
        eventData = self.tds.getEventData(self.node["thingEvent"])
        self.state["payload"] = eventData
        if self.state["payload"] == None:
            return
        
        if self.state["payload"]["type"] != "object":
            self.state["payload"]["source"] = {"type":"event", "name": self.node["thingEvent"], "id": self.node["id"]}
        
        for property in self.state["payload"]["properties"].values():
            property["source"] = {"type":"event", "name": self.node["thingEvent"], "id": self.node["id"]}

    def match(self, subflow_matches):
        children = self.getChildren()
        matches = {}

        for child in children:
            if child.node["type"] == "system-action-node" or (child.node["type"] == "system-property-node" and child.node["mode"] == "write"):
                matches[child.node["id"]] = child.match(subflow_matches)

        left_over = copy.deepcopy(subflow_matches) # Adjust scores for left over cases- e.g. not enough nodes in real flow compared to true flow

        return {"matches": matches, "left_over": left_over}

    # def extractConditions(self):
    #     conditions = []
    #     for i in self.getChildren():
    #         conditions += i.extractConditions()
    #     return conditions

class SystemPropertyNode(InteractionNode):
    def __init__(self, node, flow, tds, incomingState, incomingConditions = [], previousInteractions = []):
        super().__init__(node, flow, tds, incomingState, incomingConditions, previousInteractions)

    
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
        
        if self.state["payload"] == {}:
            return False

        propertyInput = self.tds.getPropertyValue(self.node["thingProperty"])
        payload = self.state["payload"]

        if (payload["type"] != "object") and ("source" in payload):
            del payload["source"]
        else:
            for property in payload["properties"].values():
                if "source" in property:
                    del property["source"]

        if sorted(payload) == sorted(propertyInput):
            return True
        
        self.errors[self.node["id"]].append("expected: " + json.dumps(propertyInput) + " got: " + json.dumps(payload))
        return False
    
    def conditionsMatch(self, conditions):
        if conditions == self.conditions:
            return True

    def inputMatch(self, input):
        if not self.validatePayload():
            return False
        
        if (input["type"] != "object") and (self.incomingState["payload"]["type"] != "object"):
            if "source" not in input:
                return True
            
            i_source = input["source"]
            p_source = self.incomingState["payload"]["source"]

            if i_source["type"] != p_source["type"]: # Does this need a closing else?
                return False
                
            if i_source["type"] == "event":
                return True
            
            if "name" not in i_source:
                return True
            
            if i_source["name"] != p_source["name"]:
                return True
            
            if "pos" not in i_source:
                return True
            
            if i_source["pos"] == "last": # Finish this
                return False
            
            for interaction in reversed(self.previousInteractions):
                name = None

                if interaction.node["type"] == "system-action-node":
                    name = interaction.node["thingAction"]

                if interaction.node["type"] == "system-property-node":
                    name = interaction.node["thingProperty"]

                if name != input["name"]:
                    continue
                
                if p_source["id"] == interaction.node["id"]:
                    return True
                
                return False
                
        elif (input["type"] == "object") and (self.incomingState["payload"]["type"] == "object"):
            for k, v in input["properties"].items():
                if k not in self.incomingState["payload"]["properties"]:
                    return False
                
                if "source" in v:
                    return True
                
                i_source = v["source"]
                p_source = self.incomingState["payload"]["properties"][k]["source"]

                if i_source["type"] != p_source["type"]:
                    continue
                
                if i_source["type"] == "event":
                    return True
                    
                if "name"  not in i_source:
                    return True
                
                if i_source["name"] != p_source["name"]:
                    return True
                
                if "pos" not in i_source:
                    return True
                
                if i_source["pos"] != "last": # Finish this
                    return False
                
                lastInteraction = self.previousInteractions[-1]
                name = None
                
                if lastInteraction.node["type"] == "system-action-node":
                    name = lastInteraction.node["thingAction"]

                if lastInteraction.node["type"] == "system-property-node":
                    name = lastInteraction.node["thingProperty"]

                if name == input["name"]:        
                    return True
                
                return False
        
        return False

    def preConditionsMatch(self, pre_nodes):
        if pre_nodes == []:
            return True
        
        prev = []

        for interaction in self.previousInteractions:
            if (interaction.node["type"] == "system-action-node") and (interaction.node["thingAction"] in pre_nodes):
                prev.append(interaction.node["thingAction"])
            if (interaction.node["type"] == "system-property-node") and (interaction.node["mode"] == "write") and (interaction.node["thingProperty"] in pre_nodes):
                prev.append(interaction.node["thingProperty"])

        if pre_nodes != prev:
            return False
        
        return True

    def match(self, subflow_matches):
        candidates = []

        for i in subflow_matches:
            if i[0] == self.node["thingProperty"]:
                candidates.append(i)
        
        match = {"preConditionMatch": False, "conditionsMatch": False, "inputMatch": False}
        candidates = [x for x in candidates if self.preConditionsMatch(x[1]["pre_nodes"])]

        if candidates != []:
            match["preConditionMatch"] = True
            candidates = [x for x in candidates if self.conditionsMatch(x[1]["conditions"])]
            
            if candidates != []:
                match["conditionsMatch"] = True
                candidates = [x for x in candidates if self.inputMatch(x[1]["input"])]

                if candidates != []:
                    match["inputMatch"] = True

        for candidate in candidates: # Should be no more than one candidate but just in case checks list, this check prevents multiple nodes matching against the same case.
            subflow_matches.remove(candidate)

        status = match["preConditionMatch"] and match["conditionsMatch"] and match["inputMatch"]
        return {"status": status, "match": match, "candidates": candidates}
