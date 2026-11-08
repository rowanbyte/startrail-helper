package cn.startrail.helper;

/** Pure local battle policy: two 2+3 cost cycles per initial ten energy. */
final class BattlePlan {
    enum Action { IGNITE, COMBUSTION, GATHER }
    int next=0, energy=10;
    Action action(Integer observedEnergy) {
        int available=observedEnergy==null?energy:Math.max(0,Math.min(10,observedEnergy));
        int cost=next==0?2:3;
        return available<cost?Action.GATHER:(next==0?Action.IGNITE:Action.COMBUSTION);
    }
    void confirm(Action action,Integer observedAfter) {
        if(action==Action.GATHER)energy=observedAfter==null?10:observedAfter;
        else { energy=observedAfter==null?Math.max(0,energy-(action==Action.IGNITE?2:3)):observedAfter; next=1-next; }
    }
    void reset(){next=0;energy=10;}
}
