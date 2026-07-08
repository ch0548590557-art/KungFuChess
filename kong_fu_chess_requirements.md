# Kong-Fu-Chess Project Requirements Document

> This document is based on the project requirements presented in the video and has been organized into a structured specification for a development agent or software development team.

---

# 1. General Description

Kong-Fu-Chess is a **real-time chess game** in which **both players move simultaneously**, without turns. Every chess piece requires physical time to travel from its current square to its destination—the movement is **not instantaneous**.

---

# 2. Core Game Rules (Required for the First Implementation)

## 2.1 Real-Time Movement

* There are no turns—both players may move pieces at any time, simultaneously.
* Every movement has a **travel time**. A piece is considered to be "in transit" until it reaches its destination and does not instantly appear on the target square.

## 2.2 Cooldown

* After completing a move and arriving at its destination, a piece enters a **cooldown period** before it can move again.
* Visually, the cooldown is represented by an animation—a **yellow overlay gradually shrinking** over the piece—to indicate the remaining cooldown time.

## 2.3 Win Condition

* **A player wins only by physically capturing the opponent's king.**
* **There is no concept of Check or Checkmate** in this game.
* Since pieces require time to travel, a king may escape before an attacking piece reaches it.
* The game continues until the king is actually captured.

## 2.4 Move Notation

The game uses standard chess notation (similar to algebraic notation):

* The first letter identifies the moving piece (e.g., `N` = Knight).
* The following square specifies the destination (e.g., `C6`).
* Example:

  * `NC6` → Knight moves to C6.
* Pawn moves omit the piece letter (e.g., `E4`).
* `O-O` represents castling.
* `X` indicates a capture.

Unlike traditional chess:

* Each player has **their own independent move history column**, since there are no alternating turns.
* Every move includes a **server timestamp**, representing the moment the server accepted the command—not the client's local time.

## 2.5 Score System

The interface displays each player's score based on captured material.

Piece values:

* Pawn = 1 point
* Knight = 3 points
* Bishop = 3 points
* Rook = 5 points
* Queen = 9 points
* King = Infinite (capturing it immediately ends the game)

### Pawn Promotion

* When a pawn reaches the final rank and promotes to a queen, the player immediately receives the queen's value (9 points), even if no capture occurred.
* This bonus is added to any score already accumulated.

The displayed score represents the material advantage or total score difference between the two players.

## 2.6 Player Names

When playing online, both players' names should be displayed—one above the board and one below it.

---

# 3. Extended Requirements (Future Features)

These features do not need to be implemented immediately but **must be considered during the system design**.

## 3.1 Dodge / Jump Command

Pieces can perform a **jump in place** without moving to another square.

Typical use case:

* If an enemy piece is attempting to capture one of my pieces, I may command my piece to jump.

Rules:

* The cooldown after a jump is **shorter** than after a normal movement because no actual board movement occurs.

Collision behavior:

* If the attacking piece reaches the square while my piece is still performing its jump, **my piece lands on the attacker and captures it.**
* If my piece lands before the attacker arrives, it immediately enters cooldown, allowing the attacker to capture it normally.
* Therefore, the outcome depends entirely on the relative timing between the jump landing and the attacker's arrival.

---

## 3.2 Support for Additional Piece Types (Extensible Piece System)

A major design goal is that **new piece types can be added with minimal changes to the existing codebase.**

### Example: Drone

Characteristics:

* Moves more slowly than standard chess pieces.
* May move to any empty square within a **2-square radius** (a square centered on itself extending two squares in every direction).
* This includes every empty square inside the area—not only straight lines or diagonals.

### Practical implication

The definition of a piece type should be modular.

Movement rules, movement speed, and special behaviors should belong to dedicated components (configuration, classes, interfaces, etc.) rather than being hardcoded into a central game logic.

---

## 3.3 Animation System

The cooldown animation already exists (yellow overlay).

### Idle Animation

* Pieces should have subtle breathing or idle movement instead of remaining perfectly static.

### Movement Animation

* Pieces should visually walk, hop, or otherwise animate while traveling to their destination.

### Cooldown Animation

* Pieces should display a distinct animation while recovering during cooldown.

### Extensibility

The animation system should make it easy to replace or improve animations in the future.

Initial implementations may use simple effects (color changes, scaling, etc.), while more sophisticated animations can be introduced later.

---

## 3.4 Server Architecture and Scalability

This requirement concerns the infrastructure rather than the gameplay itself.

The server architecture should be designed so that it can theoretically scale to **millions of concurrent players**.

Requirements:

* A **matchmaking system** pairs players into games.
* With sufficient hardware resources, the architecture should support a very large number of simultaneous users.
* The networking protocol should avoid communication bottlenecks that could negatively impact gameplay responsiveness.
* Client-server communication should therefore be designed with scalability and efficiency in mind, even if the initial implementation is relatively simple.

---

# 4. Design Principles

## 4.1 Measured Flexibility

Design the code so that it is easy to add foreseeable future features, including:

* New piece types
* New animations
* New commands (such as Jump)

However:

* Do **not** introduce excessive abstraction, interfaces, or architectural layers "just in case."
* Unused flexibility increases maintenance cost without providing value.

The goal is a balanced architecture that is clean today while accommodating the realistic future extensions described in Section 3.

---

## 4.2 Separate Today's Requirements from Tomorrow's Features

The requirements in **Section 2** constitute the core gameplay and must be fully implemented first.

The features in **Section 3** do not require immediate implementation, but the architecture (data model, piece system, animation interfaces, networking design, etc.) should anticipate them so they can later be added without major refactoring.

---

## 4.3 Server as the Source of Truth

Every move is recorded using the **server timestamp**, not the client's clock.

This timestamp serves as the authoritative source for resolving timing-dependent interactions, such as determining which event occurred first during collisions (e.g., Jump versus Capture).

---

# 5. Summary Table

| #  | Requirement                                  | Status             | Notes                                 |
| -- | -------------------------------------------- | ------------------ | ------------------------------------- |
| 1  | Real-time movement (no turns)                | Required (MVP)     |                                       |
| 2  | Physical movement time between squares       | Required (MVP)     |                                       |
| 3  | Cooldown after movement                      | Required (MVP)     |                                       |
| 4  | Victory by physically capturing the king     | Required (MVP)     | No Check, Checkmate, or Stalemate     |
| 5  | Move notation with server timestamps         | Required (MVP)     | Separate move history for each player |
| 6  | Material-based scoring system                | Required (MVP)     | Includes promotion bonus              |
| 7  | Display player names                         | Required (MVP)     |                                       |
| 8  | Jump / Dodge command                         | Future extension   | Timing logic should be anticipated    |
| 9  | Additional piece types (e.g., Drone)         | Future extension   | Piece architecture should be modular  |
| 10 | Animations (Idle, Movement, Cooldown)        | Future extension   | Start simple, improve later           |
| 11 | Scalable server architecture and matchmaking | System requirement | Separate from gameplay logic          |

---

*This document serves as the primary specification for the development of Kong-Fu-Chess. It defines both the core gameplay mechanics and the expected future extensions while emphasizing the project's guiding design principles: measured flexibility, clear separation between current and future requirements, and a server-authoritative architecture.*
