package cn.startrail.helper;

public final class PolicyChecks {
    static void check(boolean condition,String label){if(!condition)throw new AssertionError(label);}
    public static void main(String[] args){
        for(String preference:new String[]{"blue","purple"}){
            ResourcePolicy.Choice own=preference.equals("blue")?ResourcePolicy.Choice.BLUE:ResourcePolicy.Choice.PURPLE;
            check(ResourcePolicy.flowers(preference,120,600,20)==own,"independent preference");
            check(ResourcePolicy.flowers(preference,20,20,20)==own,"exact balance");
            check(ResourcePolicy.flowers(preference,0,0,20)==ResourcePolicy.Choice.STOP,"both exhausted");
            check(ResourcePolicy.flowers(preference,null,null,20)==own,"unknown does not switch");
        }
        check(ResourcePolicy.flowers("purple",120,19,20)==ResourcePolicy.Choice.BLUE,"purple exhausted");
        check(ResourcePolicy.flowers("blue",19,600,20)==ResourcePolicy.Choice.PURPLE,"blue exhausted");
        check(ResourcePolicy.flowers("purple",null,0,20)==ResourcePolicy.Choice.UNKNOWN,"unknown alternate");
        BattlePlan plan=new BattlePlan();
        BattlePlan.Action[] cycle={BattlePlan.Action.IGNITE,BattlePlan.Action.COMBUSTION,BattlePlan.Action.IGNITE,BattlePlan.Action.COMBUSTION,BattlePlan.Action.GATHER};
        for(int i=0;i<100;i++)for(BattlePlan.Action action:cycle){check(plan.action(null)==action,"continuous battle cycle");plan.confirm(action,null);}
        plan.reset();check(plan.action(1)==BattlePlan.Action.GATHER,"early energy shortage");
        plan.confirm(BattlePlan.Action.GATHER,10);check(plan.action(10)==BattlePlan.Action.IGNITE,"gather preserves skill order");
        System.out.println("PASS: resource boundaries and 100 battle cycles");
    }
}
