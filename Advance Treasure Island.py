# Treasure Island — Combat Edition
# Adds HP/hearts, simple combat, items, random events, and checkpoint snapshots.

import sys, random, argparse, json, os, shutil
from dataclasses import dataclass, field, asdict, replace
from textwrap import fill
from typing import Optional, Callable

# ------------- UTIL -------------

RESET = "\033[0m"
CYAN = "\033[36m"


def term_width() -> int:
    return shutil.get_terminal_size(fallback=(80, 20)).columns - 2


def say(text, width=None):
    width = width or term_width()
    print(fill(text, width=width))

class InputProvider:
    def get(self, prompt: str) -> str:
        return input(prompt)


input_provider = InputProvider()


def ask(prompt, options):
    opts = {o: o for o in options}
    firsts = {}
    for o in options:
        f = o[0]
        firsts[f] = None if f in firsts else o
    while True:
        ans = input_provider.get(f"{prompt} ({'/'.join(options)}): ").strip().lower()
        if ans in opts:
            return ans
        if len(ans) == 1 and ans in firsts and firsts[ans]:
            return firsts[ans]
        print("Choose:", ", ".join(options))

def clamp(a, lo, hi): return max(lo, min(hi, a))

# ------------- GAME STATE -------------


@dataclass
class GameState:
    hp_max: int = 10
    hp: int = 10
    inventory: set = field(default_factory=set)
    consumables: dict = field(default_factory=lambda: {"berries": 0})
    gold: int = 0
    weapon: str = "fists"
    checkpoint_fn: Optional[Callable] = None
    snapshot: Optional["GameState"] = None

    def roll_damage(self) -> int:
        if self.weapon == "spear":
            return random.randint(2, 5)
        return random.randint(1, 3)

    def save_checkpoint(self, fn):
        self.checkpoint_fn = fn
        self.snapshot = replace(self)
        save_to_disk()

    def restore_checkpoint(self):
        if self.snapshot:
            restored = replace(self.snapshot)
            self.__dict__.update(restored.__dict__)


state = GameState()
pending_scene = None


@dataclass
class Enemy:
    name: str
    hp: int
    min: int
    max: int
    flee: float


def show_status():
    inv = sorted(list(state.inventory))
    bar = (f"HP {state.hp}/{state.hp_max} | Gold {state.gold} | Weapon {state.weapon} | "
           f"Berries {state.consumables['berries']} | Items {inv}")
    print(CYAN + bar + RESET)


def reset_state(base_hp):
    state.hp_max = base_hp
    state.hp = state.hp_max
    state.inventory = set()
    state.consumables = {"berries": 0}
    state.gold = 0
    state.weapon = "fists"
    state.checkpoint_fn = intro
    state.snapshot = None


def game_over(msg="Game Over."):
    global pending_scene
    print("\n" + "-" * 54)
    print(msg)
    print("-" * 54)
    choice = ask("Retry from checkpoint, restart, or quit?", ["checkpoint", "restart", "quit"])
    if choice == "quit":
        pending_scene = None
    elif choice == "restart":
        reset_state(state.hp_max)
        pending_scene = intro
    else:
        state.restore_checkpoint()
        pending_scene = state.checkpoint_fn
    return True


def save_to_disk(filename="save.json"):
    data = asdict(replace(state))
    data["inventory"] = list(data["inventory"])
    with open(filename, "w") as f:
        json.dump({"state": data, "checkpoint": state.checkpoint_fn.__name__ if state.checkpoint_fn else "intro"}, f)


def load_from_disk(filename="save.json"):
    if not os.path.exists(filename):
        return None
    with open(filename) as f:
        data = json.load(f)
    st = data["state"]
    state.hp_max = st["hp_max"]
    state.hp = st["hp"]
    state.inventory = set(st["inventory"])
    state.consumables = st["consumables"]
    state.gold = st["gold"]
    state.weapon = st["weapon"]
    state.checkpoint_fn = globals().get(data["checkpoint"], intro)
    state.snapshot = replace(state)
    return state.checkpoint_fn

# ------------- RANDOM EVENTS -------------

def random_event(pool):
    """pool: list of (weight, callable) -> bool"""
    total = sum(w for w, _ in pool)
    r = random.uniform(0, total)
    upto = 0
    for w, ev in pool:
        if upto + w >= r:
            return ev()
        upto += w
    return False

def find_berries():
    n = random.randint(1,2)
    state.consumables["berries"] += n
    say(f"You find wild **berries** (x{n}). They smell sweet—might restore a little vigor.")
    return False

def find_spear():
    if state.weapon != "spear":
        state.weapon = "spear"
        say("You lash driftwood to a sharpened bone: **You crafted a spear** (better damage).")
    else:
        say("You find another worn pole—not better than your current spear.")
    return False

def find_rope():
    if "rope" not in state.inventory:
        state.inventory.add("rope")
        say("You find a sturdy **rope**.")
    else:
        say("You spot the old **rope** you left earlier and move on.")
    return False


def find_torch():
    if "torch" not in state.inventory:
        state.inventory.add("torch")
        say("You find a waterproof **torch**.")
    else:
        say("You find spent torches half buried in sand.")
    return False

def serpent_ambush():
    say("A **lake serpent** erupts from the water!")
    enemy = Enemy("Lake Serpent", 8, 1, 4, 0.35)
    return combat(enemy)

def beast_attack():
    say("Shadowy **beasts** prowl from the ruins!")
    enemy = Enemy("Beasts", 7, 1, 3, 0.5)
    return combat(enemy)

# ------------- COMBAT -------------

def heal_with_berries():
    if state.consumables["berries"] <= 0:
        print("You have no berries.")
        return False
    state.consumables["berries"] -= 1
    healed = 3
    state.hp = clamp(state.hp + healed, 0, state.hp_max)
    say(f"You eat berries and recover {healed} HP. (Now {state.hp}/{state.hp_max})")
    return True

def combat(enemy: Enemy):
    say(f"Combat begins vs **{enemy.name}**!")
    defend_buff = False
    while state.hp > 0 and enemy.hp > 0:
        show_status()
        choice = ask("Action?", ["attack", "defend", "item", "flee"])
        print()
        enemy_attacks = True
        if choice == "attack":
            dmg = state.roll_damage()
            enemy.hp -= dmg
            say(f"You strike with your {state.weapon} for {dmg} damage. ({enemy.name} HP {max(0, enemy.hp)})")
        elif choice == "defend":
            defend_buff = True
            say("You brace yourself, watching the enemy closely.")
        elif choice == "item":
            used = heal_with_berries()
            if used:
                enemy_attacks = False
        else:  # flee
            if random.random() < enemy.flee:
                say("You slip away into the shadows!")
                return
            else:
                say("You try to flee but stumble—no escape!")

        if enemy.hp > 0 and enemy_attacks:
            edmg = random.randint(enemy.min, enemy.max)
            if defend_buff:
                edmg = max(0, edmg - 2)
            defend_buff = False
            state.hp -= edmg
            say(f"{enemy.name} hits you for {edmg} damage. (HP {max(0, state.hp)}/{state.hp_max})")
        else:
            defend_buff = False
        print()
    if state.hp <= 0:
        game_over("You were defeated.")
        return True
    say(f"You defeated the {enemy.name}!")
    loot_gold = random.randint(1, 2)
    state.gold += loot_gold
    say(f"You scavenge **{loot_gold} gold**.")
    return False
# ------------- SCENES -------------

def intro():
    print("\n" + "=" * term_width())
    print("Welcome to Treasure Island — Combat Edition")
    print("Your mission is to find the treasure and live to tell the tale.")
    print("=" * term_width() + "\n")
    state.save_checkpoint(crossroad)
    return crossroad

def crossroad():
    state.save_checkpoint(crossroad)
    say("A lonely crossroad beside an old signpost. Forest whispers to the **left**; "
        "a worn path dips to the **right**. You could also **look** around.")
    choice = ask("What do you do?", ["left", "right", "look"])
    if choice == "look":
        say("You scan the ground carefully.")
        if random_event([
            (5, lambda: False),
            (6, find_berries),
            (6, find_rope),
            (3, beast_attack),
        ]):
            return pending_scene
        return crossroad
    if choice == "left":
        return lakeshore
    else:
        return pitfall

def pitfall():
    say("You follow the path to the right. The ground crumbles—")
    if "rope" in state.inventory:
        say("You anchor the rope to a root and climb out. At the bottom you noticed a glint: **+1 gold**.")
        state.gold += 1
        return crossroad
    game_over("You fall into a deep hole. Game Over.")
    return pending_scene


def lakeshore():
    state.save_checkpoint(lakeshore)
    say("The forest thins into a moonlit **lake**. A small island rests far out.")
    # random shoreline events (low chance of serpent ambush)
    if random_event([
        (8, lambda: False),
        (4, find_berries),
        (2, serpent_ambush),
    ]):
        return pending_scene
    choice = ask("Do you **swim** across or **wait** by the shore?", ["swim", "wait"])
    if choice == "swim":
        if random.random() < 0.2 and "rope" in state.inventory:
            say("With the rope and grit, you barely make it through currents to the island.")
            return island
        else:
            say("The current overpowers you. You wash back ashore, battered.")
            state.hp = clamp(state.hp - 3, 0, state.hp_max)
            if state.gold > 0:
                state.gold -= 1
                say("A coin pouch slips away in the waves (-1 gold).")
            if state.hp <= 0:
                game_over("You succumb to the lake.")
                return pending_scene
            return lakeshore
    else:
        return ferry

def ferry():
    say("You wait. Mist rolls in. A silent skiff edges from the fog—"
        "a hooded ferryman extends a hand.")
    if state.gold > 0:
        choice = ask("**Pay** 1 gold, answer a **riddle**, or **decline**?", ["pay", "riddle", "decline"])
    else:
        choice = ask("You have no coin. Try a **riddle** or **decline**?", ["riddle", "decline"])

    if choice == "decline":
        say("You step back. The skiff glides away.")
        return lakeshore

    if choice == "pay" and state.gold > 0:
        state.gold -= 1
        say("The ferryman nods and delivers you safely to the island.")
        return island

    say('Ferryman: "Answer true and the lake will part for you."')
    say("RIDDLE: I speak without a mouth and hear without ears. I have nobody, "
        "but I come alive with wind. What am I?")
    answers = {"echo"}
    attempt = 0
    while attempt < 2:
        ans = input_provider.get("Your answer: ").strip().lower()
        if ans in answers:
            say("Ferryman: \"Correct.\" Passage is granted.")
            return island
        else:
            attempt += 1
            say("Ferryman: \"Incorrect.\"")
            if attempt < 2:
                say("Try again...")
    if random.random() < 0.5:
        say("Something brushes your ankle—teeth! You lose 2 HP escaping the shallows.")
        state.hp = clamp(state.hp - 2, 0, state.hp_max)
        if state.hp <= 0:
            game_over("You succumb to your wounds.")
            return pending_scene
    return lakeshore

def island():
    state.save_checkpoint(island)
    say("You arrive unharmed at the island. A path leads to a lonely **house**. "
        "You could also **explore** the beach.")
    choice = ask("Where to?", ["house", "explore"])
    if choice == "explore":
        say("You comb the shoreline.")
        if random_event([
            (5, find_berries),
            (5, find_spear),
            (3, find_torch),
            (3, serpent_ambush),
        ]):
            return pending_scene
        return island
    else:
        return house

def house():
    state.save_checkpoint(house)
    say("Inside the ruined house, a hall ends in three doors: **red**, **blue**, **yellow**.")
    # chance for beasts before you choose
    if random_event([
        (9, lambda: False),
        (3, beast_attack),
    ]):
        return pending_scene
    choice = ask("Which door?", ["red", "blue", "yellow"])

    if choice == "red":
        # torch can mitigate burn via defend/berries, but still lethal; keep canonical loss
        game_over("You open the red door. A wall of flame engulfs the hall. Burned by fire. Game Over.")
        return pending_scene
    elif choice == "yellow":
        return treasure_room
    else:  # blue
        if "torch" in state.inventory:
            say("You light your torch and peek in. Eyes glitter—beasts recoil from the flame. "
                "On the wall, a scrawl: 'Gold shines where patience wins.' You back out safely.")
            return house
        else:
            # final combat chance to survive canonical 'beasts' end
            say("Darkness and low snarls surround you...")
            enemy = Enemy("Ravenous Beasts", 8, 1, 3, 0.35)
            if combat(enemy):
                return pending_scene
            say("You stagger back into the hall, bloodied but alive.")
            return house

def treasure_room():
    say("The yellow door opens to a skylit chamber. A chest rests on a stone plinth.")
    say("Inside lies the **Treasure of the Patient** and a note: "
        "'Those who waited earned passage; those who looked found help.'")
    print("\n✨ YOU WIN! ✨\n")
    return postgame

def postgame():
    show_status()
    choice = ask("Play again?", ["yes", "no"])
    if choice == "yes":
        reset_state(state.hp_max)
        return intro
    else:
        say("Thanks for playing, adventurer!")
        sys.exit(0)

# ------------- RUN -------------


def play(start_scene):
    scene = start_scene
    while scene:
        show_status()
        scene = scene()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--easy", action="store_true")
    parser.add_argument("--hard", action="store_true")
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()

    base_hp = 10
    if args.easy:
        base_hp += 5
    if args.hard:
        base_hp -= 3

    if args.seed is not None:
        random.seed(args.seed)
    else:
        random.seed()

    reset_state(base_hp)
    start_scene = intro
    if args.load:
        loaded = load_from_disk()
        if loaded:
            start_scene = loaded

    play(start_scene)


if __name__ == "__main__":
    main()
