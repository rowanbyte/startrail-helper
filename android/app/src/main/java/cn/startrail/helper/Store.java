package cn.startrail.helper;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

final class Store {
    static volatile String status="尚未开始", detail="开启无障碍后，可读取游戏实时目标";
    static volatile boolean active=false, paused=false;
    static final ArrayList<String> logs=new ArrayList<>();
    static final ArrayList<Models.Target> targets=new ArrayList<>();
    static volatile int quota=-1, round=0, total=2, succeeded=0, failed=0;
    static Context context;
    static SharedPreferences prefs;

    static void init(Context c) {
        if(context!=null)return;
        context=c.getApplicationContext(); prefs=context.getSharedPreferences("helper",0);
        try {
            JSONArray a=new JSONArray(prefs.getString("targets","[]"));
            for(int i=0;i<a.length();i++) targets.add(Models.Target.from(a.getJSONObject(i)));
        } catch(JSONException ignored){}
    }
    static void state(String text) { status=text; log(text); }
    static void log(String text) {
        String line=new SimpleDateFormat("HH:mm:ss",Locale.CHINA).format(new Date())+"  "+text;
        synchronized(logs) { logs.add(line); while(logs.size()>300)logs.remove(0); }
        android.util.Log.i("Startrail",text);
        if(context!=null) try {
            File file=new File(context.getFilesDir(),"session.log");
            if(file.length()>2_000_000) { File old=new File(context.getFilesDir(),"session.previous.log"); if(old.exists())old.delete(); file.renameTo(old); }
            try(FileWriter writer=new FileWriter(file,true)){writer.write(line+"\n");}
        } catch(IOException ignored){}
    }
    static void saveTargets() {
        JSONArray a=new JSONArray(); synchronized(targets){for(Models.Target t:targets)a.put(t.json());}
        prefs.edit().putString("targets",a.toString()).putLong("scanned",System.currentTimeMillis()).apply();
    }
    static Models.Config config() { try{return Models.Config.from(new JSONObject(prefs.getString("config","{}")));}catch(JSONException e){return new Models.Config();} }
    static void saveConfig(Models.Config c){prefs.edit().putString("config",c.json().toString()).apply();}
    static String logText(){synchronized(logs){return String.join("\n",logs);}}
}
