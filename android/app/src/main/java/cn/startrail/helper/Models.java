package cn.startrail.helper;

import org.json.*;

final class Models {
    static final class Target {
        String id, name, category; long signature;
        Target(String id, String name, String category, long signature) {
            this.id=id; this.name=name; this.category=category; this.signature=signature;
        }
        JSONObject json() {
            JSONObject j=new JSONObject();
            try { j.put("id",id).put("name",name).put("category",category).put("signature",signature); } catch(JSONException ignored){}
            return j;
        }
        static Target from(JSONObject j) { return new Target(j.optString("id"), j.optString("name"),j.optString("category","flowers"),j.optLong("signature")); }
    }
    static final class Config {
        String category="flowers", resource="purple", targetId="", targetName="";
        int runs=2, slot=5;
        JSONObject json() {
            JSONObject j=new JSONObject();
            try { j.put("category",category).put("resource",resource).put("targetId",targetId).put("targetName",targetName).put("runs",runs).put("slot",slot); } catch(JSONException ignored){}
            return j;
        }
        static Config from(JSONObject j) {
            Config c=new Config(); c.category=j.optString("category","flowers"); c.resource=j.optString("resource","purple");
            c.targetId=j.optString("targetId"); c.targetName=j.optString("targetName"); c.runs=j.optInt("runs",2); c.slot=j.optInt("slot",5); return c;
        }
    }
}
