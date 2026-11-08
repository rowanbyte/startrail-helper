package cn.startrail.helper;

import android.content.Context;
import android.graphics.*;
import java.io.*;
import java.util.*;

/** Debug-only local OCR regression. Never sends gestures or opens the game. */
final class LocalSelfTest {
    final Context context; final Vision vision=new Vision();int index=0;
    final String[] files={"world.png","manual.png","catalog.png","battle.png","capture.png","reward.png","reward_android.png","world_after_reward.png"};
    LocalSelfTest(Context context){this.context=context;}
    void run(){
        BattlePlan plan=new BattlePlan();BattlePlan.Action[] expected={BattlePlan.Action.IGNITE,BattlePlan.Action.COMBUSTION,BattlePlan.Action.IGNITE,BattlePlan.Action.COMBUSTION,BattlePlan.Action.GATHER};
        for(BattlePlan.Action action:expected){if(plan.action(null)!=action)throw new AssertionError("Battle energy policy");plan.confirm(action,null);}
        Store.log("SELFTEST energy policy PASS");next();
    }
    void next(){
        if(index>=files.length){Store.log("SELFTEST COMPLETE");vision.close();return;}
        String name=files[index++];
        File local=new File(context.getFilesDir(),"fixture_"+name);
        try(InputStream input=local.isFile()?new FileInputStream(local):context.getAssets().open("fixtures/"+name)){
            Bitmap bitmap=BitmapFactory.decodeStream(input);
            vision.read(bitmap,frame->{
                boolean pass=switch(name){
                    case "world.png" -> frame.has("触碰","挑战");
                    case "world_after_reward.png" -> frame.has("挑战");
                    case "manual.png" -> frame.has("目标进度","学院作业");
                    case "catalog.png" -> frame.matching("传送").size()>=3;
                    case "battle.png" -> frame.has("引燃")&&frame.has("充分燃烧");
                    case "capture.png" -> frame.has("捕捉消耗","本次专属")&&frame.currencyPoint(false)!=null&&frame.currencyPoint(true)!=null&&frame.currencyPoint(false)[0]<frame.currencyPoint(true)[0];
                    case "reward.png", "reward_android.png" -> frame.has("获得奖励","获得奖");
                    default -> false;
                };
                if(!name.startsWith("reward")&&frame.has("获得奖励"))pass=false;
                if(name.equals("reward_android.png")){
                    Engine reader=new Engine(null);reader.stage=Engine.Stage.CAPTURE;
                    if(reader.reward(frame)){reader.step(frame);pass&=reader.stage==Engine.Stage.REWARD;}else pass=false;
                    reader.vision.close();
                }
                if(name.equals("world_after_reward.png")){
                    Engine reader=new Engine(null);reader.stage=Engine.Stage.REWARD;reader.stageSince=reader.now()-2000;reader.rewardStep(frame);
                    pass&=reader.stage==Engine.Stage.EXIT;reader.vision.close();
                }
                Store.log("SELFTEST "+name+" "+(pass?"PASS":"FAIL"));
                if(name.equals("capture.png"))Store.log("SELFTEST capture cost="+frame.captureCost()+" blue="+frame.blue()+" purple="+frame.purple());
                if(name.equals("catalog.png")){
                    Engine reader=new Engine(null);reader.config=new Models.Config();reader.config.category="legends";
                    Store.log("SELFTEST catalog rows="+reader.rows(frame).size());reader.vision.close();
                }
                try(FileWriter writer=new FileWriter(new File(context.getFilesDir(),"selftest_"+name+".txt"))){writer.write(frame.all());}catch(IOException ignored){}
                frame.bitmap.recycle();next();
            },error->{Store.log("SELFTEST FAIL "+name+" "+error.getMessage());next();});
        }catch(Exception error){Store.log("SELFTEST skip "+name);next();}
    }
}
