from typing import List, Tuple, Dict

from kungfu_chess.realtime.motion import Motion, MotionKind


class CollisionResolver:
    _ACTION_PRIORITY = [MotionKind.JUMP, MotionKind.MOVE]

    @staticmethod
    def resolve(arrived: List[Motion]) -> Tuple[List[Motion], List[Motion], List[Motion]]:
        groups: Dict[int, List[Motion]] = {}
        for motion in arrived:
            groups.setdefault(motion.arrival_time_ms, []).append(motion)

        arrivals: List[Motion] = []
        killed: List[Motion] = []
        canceled: List[Motion] = []

        for arrival_time in sorted(groups):
            group = groups[arrival_time]
            destination_groups: Dict[tuple[int, int], List[Motion]] = {}
            for motion in group:
                key = (motion.destination.row, motion.destination.col)
                destination_groups.setdefault(key, []).append(motion)

            for motions in destination_groups.values():
                if len(motions) == 1:
                    arrivals.append(motions[0])
                    continue

                survivor = CollisionResolver._choose_survivor(motions)
                arrivals.append(survivor)
                for motion in motions:
                    if motion is survivor:
                        continue
                    if CollisionResolver._is_canceled_by(survivor, motion):
                        canceled.append(motion)
                    else:
                        killed.append(motion)

        return arrivals, killed, canceled

    @staticmethod
    def _choose_survivor(motions: List[Motion]) -> Motion:
        return sorted(
            motions,
            key=lambda m: (
                CollisionResolver._ACTION_PRIORITY.index(m.action_kind),
                m.start_time_ms,
                m.piece_id,
            )
        )[0]

    @staticmethod
    def _is_canceled_by(survivor: Motion, loser: Motion) -> bool:
        return CollisionResolver._ACTION_PRIORITY.index(survivor.action_kind) < \
            CollisionResolver._ACTION_PRIORITY.index(loser.action_kind)
