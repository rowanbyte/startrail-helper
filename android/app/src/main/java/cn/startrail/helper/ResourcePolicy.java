package cn.startrail.helper;

/** Unknown balances never authorize spending a different resource. */
final class ResourcePolicy {
    enum Choice { BLUE, PURPLE, STOP, UNKNOWN }
    static Choice flowers(String preference,Integer blue,Integer purple,Integer cost){
        Choice preferred="blue".equals(preference)?Choice.BLUE:Choice.PURPLE;
        Integer first=preferred==Choice.BLUE?blue:purple,second=preferred==Choice.BLUE?purple:blue;
        if(cost==null||cost<=0||first==null)return preferred;
        if(first>=cost)return preferred;
        if(second==null)return Choice.UNKNOWN;
        if(second<cost)return Choice.STOP;
        return preferred==Choice.BLUE?Choice.PURPLE:Choice.BLUE;
    }
}
