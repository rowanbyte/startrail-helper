package cn.startrail.helper;

import android.graphics.Bitmap;
import android.os.SystemClock;
import org.json.*;
import java.io.*;
import java.util.*;

/** One local, observed-frame state machine. No queued clicks survive a pause. */
final class Engine {
    enum Stage { NAV, RESET, SCAN, FIND, MAP, APPROACH, ENTER, BATTLE, FAINT, CAPTURE, REWARD, EXIT, RECOVER }
    final GameAccessibilityService service;
    final Vision vision=new Vision();
    Models.Config config;
    Models.Target target;
    Stage stage=Stage.NAV;
    boolean scanOnly, busy, tabChosen, partySelected, pickerChosen, rewardSeen;
    int generation=0, steps=0, stalls=0, navAttempts=0, settle=0, captureStep=0, captureRetries=0;
    long stageSince, nextAt, battleSince, faintSince, pendingSince, pauseSince, gestureSince;
    String lastRows="", selectedCurrency="";
    String stopAfterExit="";
    BattlePlan plan=new BattlePlan();
    BattlePlan.Action pending;
    Integer beforeEnergy;
    boolean activationSeen;
    boolean pickerVerified=false;
    final HashSet<String> exhaustedCurrencies=new HashSet<>();
    Integer knownCaptureCost=null;
    int skillRetries=0, screenshotFailures=0;
    final ArrayList<JSONObject> outcomes=new ArrayList<>();
    final ArrayList<Models.Target> scannedTargets=new ArrayList<>();
    final Runnable loop=this::tick;

    Engine(GameAccessibilityService service){this.service=service;}
    long now(){return SystemClock.elapsedRealtime();}
    void scan(String category){
        stopQuiet();config=new Models.Config();config.category=category;scanOnly=true;target=null;
        scannedTargets.clear();
        begin();Store.state("准备读取实时目标");service.openGame();
    }
    void start(Models.Config config){
        stopQuiet();this.config=config;scanOnly=false;
        synchronized(Store.targets){target=Store.targets.stream().filter(t->t.id.equals(config.targetId)&&t.category.equals(config.category)).findFirst().orElse(null);}
        if(target==null){Store.state("请先读取实时列表并选择目标");return;}
        if(config.runs<1||config.runs>100||config.slot<1||config.slot>6){Store.state("次数或出战位置不正确");return;}
        if(config.category.equals("legends")&&!config.resource.equals("blue")&&!config.resource.equals("legendary")){Store.state("传说精灵只能选择蓝星周次数或专用印记");return;}
        Store.saveConfig(config);outcomes.clear();Store.round=1;Store.total=config.runs;Store.succeeded=0;Store.failed=0;
        begin();Store.state("准备连刷："+target.name);service.openGame();
    }
    void begin(){
        generation++;busy=false;Store.active=true;Store.paused=false;tabChosen=false;navAttempts=0;
        rewardSeen=false;pending=null;partySelected=false;pickerChosen=false;plan.reset();
        stopAfterExit="";
        setStage(Stage.NAV,"打开挑战手册");service.showOverlay();schedule(700);
    }
    void setStage(Stage value,String label){stage=value;stageSince=now();steps=0;stalls=0;settle=0;lastRows="";if(value==Stage.CAPTURE){exhaustedCurrencies.clear();knownCaptureCost=null;selectedCurrency=config.resource;}Store.state(label);}
    void schedule(long delay){service.handler.removeCallbacks(loop);if(Store.active&&!Store.paused)service.handler.postDelayed(loop,Math.max(450,delay));}
    void pause(String reason){if(!Store.active)return;Store.paused=true;pauseSince=now();generation++;busy=false;service.handler.removeCallbacks(loop);Store.state(reason);service.updateOverlay();}
    void resume(){if(!Store.active||!Store.paused)return;long delta=now()-pauseSince;stageSince+=delta;battleSince+=delta;pendingSince+=delta;if(faintSince!=0)faintSince+=delta;Store.paused=false;generation++;Store.state("继续："+stage);service.openGame();schedule(600);}
    void stopQuiet(){generation++;Store.active=false;Store.paused=false;busy=false;service.handler.removeCallbacks(loop);pending=null;}
    void stop(String reason){stopQuiet();Store.state(reason);saveSummary();service.hideOverlay();}
    void fail(String reason){
        Store.log("第 "+Store.round+" 轮失败："+reason);record(false,reason);setStage(Stage.RECOVER,"本轮失败，退出后继续下一轮");
    }
    void record(boolean success,String reason){
        try{JSONObject row=new JSONObject().put("round",Store.round).put("success",success).put("reason",reason);outcomes.add(row);}catch(JSONException ignored){}
        if(success)Store.succeeded++;else Store.failed++;saveSummary();
    }
    void saveSummary(){
        if(config==null)return;
        JSONObject json=new JSONObject();JSONArray rows=new JSONArray();for(JSONObject r:outcomes)rows.put(r);
        try{json.put("config",config.json()).put("succeeded",Store.succeeded).put("failed",Store.failed).put("outcomes",rows).put("status",Store.status);
            try(FileWriter writer=new FileWriter(new File(service.getFilesDir(),"last_run.json"))){writer.write(json.toString(2));}
        }catch(Exception e){Store.log("保存运行摘要失败："+e.getMessage());}
    }
    void tick(){
        if(!Store.active||Store.paused)return;
        service.updateOverlay();
        if(service.gestureBusy||busy||now()<nextAt){schedule(450);return;}
        if(!service.gameActive()){Store.detail="等待游戏回到前台；当前不截图、不触摸其他应用";schedule(700);return;}
        Store.detail="本地识别 · "+stage;busy=true;int token=generation;
        service.capture(bitmap->{
            if(token!=generation){bitmap.recycle();return;}
            vision.read(bitmap,frame->{
                if(token!=generation){frame.bitmap.recycle();return;}
                busy=false;screenshotFailures=0;
                try{step(frame);}catch(Exception e){diagnostic(frame,"exception");pause("流程异常："+e.getMessage());}
                finally{frame.bitmap.recycle();service.updateOverlay();schedule(500);}
            },error->{if(token!=generation)return;busy=false;pause("中文识别失败："+error.getMessage());});
        },error->{if(token!=generation)return;busy=false;if(++screenshotFailures>4)pause(error+"，请检查无障碍权限");else schedule(900);});
    }
    void tap(Vision.Item item){tap(item.x(),item.y());}
    void tap(float x,float y){if(service.tap(x,y,null))nextAt=now()+900;}
    void swipe(float x,float y,float endX,float endY,long ms){if(service.gesture(x,y,endX,endY,ms,null))nextAt=now()+ms+650;}
    boolean tabs(Vision.Frame f){return f.has("稀兽花种")&&f.has("传说精灵");}
    boolean combat(Vision.Frame f){return f.items.stream().anyMatch(i->i.key.equals("引燃")&&i.x()<.28f&&i.y()>.25f&&i.y()<.85f)&&(f.has("充分燃")||f.energy()!=null);}
    boolean capture(Vision.Frame f){return f.has("本次捕捉消耗","捕捉消耗")||(f.has("本次专属")&&f.lower("捕捉")!=null);}
    boolean reward(Vision.Frame f){return f.has("获得奖励","获得奖","获取奖励");}
    boolean result(Vision.Frame f){return f.has("再次挑战","挑战成功","捕捉成功","返回世界","挑战失败","战斗失败");}
    boolean faint(Vision.Frame f){return f.has("已力竭","已经力竭","失去战斗能力","更换精灵");}
    boolean battleUi(Vision.Frame f){return combat(f)||(f.energy()!=null&&f.lower("逃跑")!=null);}
    boolean worldUi(Vision.Frame f){
        if(battleUi(f)||capture(f)||reward(f)||result(f))return false;
        return tabs(f)||f.items.stream().anyMatch(i->i.x()>.53f&&i.y()>.3f&&i.y()<.7f&&i.key.equals("挑战"))
            ||f.items.stream().anyMatch(i->i.x()>.75f&&i.y()<.4f&&i.key.matches("[0-9]+米"));
    }
    void step(Vision.Frame f){
        if(f.bitmap.getWidth()<f.bitmap.getHeight()){pause("请将游戏切换到横屏后继续");return;}
        if(f.has("网络连接中","重新连接","网络环境不稳定","网络状态不稳定")){
            Vision.Item retry=f.lower("重试");if(retry!=null)tap(retry);
            Store.detail="游戏网络不稳定，等待恢复";nextAt=now()+4000;
            if(now()-stageSince>150000)pause("网络长时间未恢复");return;
        }
        if((stage==Stage.BATTLE||stage==Stage.FAINT||stage==Stage.ENTER)&&capture(f)){
            pending=null;captureStep=0;captureRetries=0;setStage(Stage.CAPTURE,"Boss 已击败，准备捕捉");return;
        }
        if((stage==Stage.BATTLE||stage==Stage.CAPTURE||stage==Stage.FAINT)&&reward(f)){
            rewardSeen=true;setStage(Stage.REWARD,"已确认获得奖励，退出结算");return;
        }
        switch(stage){
            case NAV -> navigate(f);
            case RESET -> reset(f);
            case SCAN -> scanPage(f);
            case FIND -> findPage(f);
            case MAP -> map(f);
            case APPROACH -> approach(f);
            case ENTER -> enter(f);
            case BATTLE -> battle(f);
            case FAINT -> waitFainted(f);
            case CAPTURE -> captureStep(f);
            case REWARD -> rewardStep(f);
            case EXIT -> exitStep(f,false);
            case RECOVER -> exitStep(f,true);
        }
    }
    void navigate(Vision.Frame f){
        if(capture(f)&&!scanOnly){
            if(!f.has(target.name)){pause("当前捕捉目标与所选目标未能核对，已保留界面");return;}
            captureStep=0;captureRetries=0;setStage(Stage.CAPTURE,"接续当前目标捕捉");return;
        }
        if(!combat(f)&&f.lower("逃跑")!=null&&f.lower("技能")!=null){tap(f.lower("技能"));return;}
        if(f.has("初始能量","应对状态")&&!combat(f)){tap(.83f,.68f);return;}
        if(combat(f)){plan.reset();pending=null;battleSince=now();faintSince=0;setStage(Stage.BATTLE,"接续当前战斗：引燃");battle(f);return;}
        if(battleUi(f)&&!scanOnly){fail("当前出战技能不符，先退出再选择燃薪虫");return;}
        if(f.has("更换出战精灵","挑战准备")){Vision.Item cancel=f.lower("取消");if(cancel!=null)tap(cancel);return;}
        if(tabs(f)){
            if(!tabChosen){Vision.Item item=f.find(config.category.equals("legends")?"传说精灵":"稀兽花种");tap(item);tabChosen=true;return;}
            setStage(Stage.RESET,"列表回到顶部");return;
        }
        if(reward(f)){tap(.82f,.72f);return;}
        if(result(f)){Vision.Item exit=f.lower("退出","返回世界","离开");if(exit!=null)tap(exit);else tap(.43f,.94f);return;}
        if(now()-stageSince>40000){diagnostic(f,"manual_not_found");stop("未能打开挑战列表，请先手动打开手册后重试");return;}
        if(f.has("学院作业","目标进度","必修","魔法师手册")){tap(.083f,.24f);return;}
        if(++navAttempts>7){diagnostic(f,"navigation");stop("未识别到挑战入口，请校准手册位置");return;}
        float[] point=point("manual",.684f,.05f);tap(point[0],point[1]);nextAt=now()+1800;
    }
    record Row(Models.Target target,Vision.Item button){}
    ArrayList<Row> rows(Vision.Frame f){
        ArrayList<Row> result=new ArrayList<>();
        for(Vision.Item button:f.matching("传送")){
            if(button.x()<.65f||button.y()<.12f)continue;
            String name="";
            for(Vision.Item i:f.items){
                if(i.x()<.27f||i.x()>.56f||i.y()<button.y()-.11f||i.y()>button.y()+.015f)continue;
                String candidate=i.key.replaceAll("[0-9]+级.*$","");
                if(!candidate.matches("[\\u3400-\\u9fff]{2,9}")||candidate.matches(".*(完成|消耗|首通|额外|传送|印记|花种|捕捉|可获得|本周).*"))continue;
                if(candidate.length()>name.length())name=candidate;
            }
            long signature=f.signature(.29f,Math.max(.14f,button.y()-.075f),.47f,button.y()-.015f);
            if(name.isEmpty())name="未识别目标·"+Long.toHexString(signature).substring(0,Math.min(4,Long.toHexString(signature).length()));
            Models.Target t=new Models.Target(config.category+":"+name,name,config.category,signature);
            result.add(new Row(t,button));
        }return result;
    }
    String rowKey(ArrayList<Row> rows){StringBuilder b=new StringBuilder();for(Row row:rows)b.append(row.target.name).append('|');return b.toString();}
    void reset(Vision.Frame f){
        if(!tabs(f)){setStage(Stage.NAV,"重新打开活动列表");tabChosen=false;return;}
        ArrayList<Row> rows=rows(f);String key=rowKey(rows);
        stalls=key.equals(lastRows)&&!key.isEmpty()?stalls+1:0;lastRows=key;
        if(stalls>=2||steps++>=14){setStage(scanOnly?Stage.SCAN:Stage.FIND,scanOnly?"读取当前活动目标":"核对目标并传送");return;}
        swipe(.50f,.30f,.50f,.78f,350);
    }
    void scanPage(Vision.Frame f){
        ArrayList<Row> rows=rows(f);String key=rowKey(rows);
        if(config.category.equals("legends")){Integer quota=f.quota();if(quota!=null)Store.quota=quota;}
        for(Row row:rows){
            boolean exists=scannedTargets.stream().anyMatch(t->t.id.equals(row.target.id));
            if(!exists){scannedTargets.add(row.target);Store.log("发现目标："+row.target.name);saveThumb(f,row);}
        }
        stalls=key.equals(lastRows)&&!key.isEmpty()?stalls+1:0;lastRows=key;
        if(stalls>=2||steps++>=40){
            long count=scannedTargets.size();
            if(count>0){
                synchronized(Store.targets){Store.targets.removeIf(t->t.category.equals(config.category));Store.targets.addAll(scannedTargets);}
                Store.saveTargets();Store.prefs.edit().putLong("scanned_"+config.category,System.currentTimeMillis()).apply();
            }
            stop(count>0?"实时列表读取完成，共 "+count+" 个目标":"未读到传送卡片，请检查挑战页");service.openHome();return;
        }
        swipe(.52f,.76f,.52f,.40f,400);
    }
    void saveThumb(Vision.Frame f,Row row){
        try{int w=f.bitmap.getWidth(),h=f.bitmap.getHeight();int top=Math.max(0,(int)((row.button.y()-.10f)*h));int height=Math.min(h-top,(int)(h*.175f));
            Bitmap crop=Bitmap.createBitmap(f.bitmap,(int)(w*.15f),top,(int)(w*.31f),height);
            try(FileOutputStream out=new FileOutputStream(new File(service.getFilesDir(),"target_"+Integer.toHexString(row.target.id.hashCode())+".png"))){crop.compress(Bitmap.CompressFormat.PNG,100,out);}crop.recycle();
        }catch(Exception ignored){}
    }
    void findPage(Vision.Frame f){
        if(!tabs(f)){setStage(Stage.NAV,"重新定位挑战列表");tabChosen=false;return;}
        ArrayList<Row> rows=rows(f);Row found=null;
        for(Row row:rows)if(row.target.name.equals(target.name)){found=row;break;}
        if(found!=null){
            if(++settle<2)return;
            if(config.category.equals("legends")&&config.resource.equals("blue")){
                Integer quota=f.quota(),balance=f.blue();Store.quota=quota==null?-1:quota;
                if(quota==null){pause("无法确认本周传说捕捉次数，未进入挑战");return;}
                if(quota==0){stop("本周契约印记传说捕捉次数已用完");return;}
                if(balance==null||balance<40){stop(balance==null?"无法确认蓝星余额":"蓝星不足 40，未改用专用印记");return;}
            }
            Store.log("目标卡片确认："+found.target.name);tap(found.button);setStage(Stage.MAP,"确认地图传送");return;
        }
        settle=0;String key=rowKey(rows);stalls=key.equals(lastRows)&&!key.isEmpty()?stalls+1:0;lastRows=key;
        if(stalls>=2||steps++>40){stop("目标已不在当前活动中，请重新读取列表");return;}
        swipe(.52f,.76f,.52f,.40f,400);
    }
    void map(Vision.Frame f){
        Vision.Item teleport=f.lower("传送");
        if(teleport!=null&&!tabs(f)){tap(teleport);setStage(Stage.APPROACH,"传送后靠近挑战点");nextAt=now()+3500;return;}
        if(!tabs(f)&&now()-stageSince>5500&&!f.has("传送")){setStage(Stage.APPROACH,"检查附近挑战提示");return;}
        if(now()-stageSince>20000){fail("传送未确认");return;}
    }
    void approach(Vision.Frame f){
        Vision.Item challenge=f.find("挑战");
        if(challenge!=null&&!tabs(f)){tap(challenge);setStage(Stage.ENTER,"进入挑战并选择出战精灵");partySelected=false;pickerChosen=false;return;}
        if(now()-stageSince>45000||steps>=28){fail("传送点附近没有找到挑战按钮");return;}
        float[] center=point("joystick",.21f,.76f);int segment=(steps/2)%4;
        float[][] directions={{0,-.065f},{.065f,0},{0,.065f},{-.065f,0}};
        float reach=1+(steps/8)*.20f;float dx=directions[segment][0]*reach,dy=directions[segment][1]*reach;
        swipe(center[0],center[1],center[0]+dx,center[1]+dy,550);steps++;
    }
    void enter(Vision.Frame f){
        if((service.getApplicationInfo().flags&android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE)!=0)diagnostic(f,"entry_latest");
        if(pickerChosen&&!combat(f)&&f.has("引燃")&&f.has("充分燃")){
            pickerVerified=true;Store.log("已核对出战技能：引燃、充分燃烧");tap(.83f,.68f);return;
        }
        if(pickerChosen&&!pickerVerified&&!combat(f)&&f.has("应对状态","初始能量")){
            diagnostic(f,"party_identity_mismatch");pause("第 "+config.slot+" 位的技能不符，请确认燃薪虫位置");return;
        }
        if(f.has("初始能量","应对状态")&&!combat(f)){tap(.83f,.68f);return;}
        if(combat(f)){plan.reset();pending=null;battleSince=now();faintSince=0;setStage(Stage.BATTLE,"战斗开始：引燃");battle(f);return;}
        if(battleUi(f)){diagnostic(f,"wrong_pet");fail("当前技能与燃薪虫策略不符，退出本轮");return;}
        if(now()-stageSince>55000){diagnostic(f,"entry_timeout");fail("进入战斗超时");return;}
        if(f.items.stream().anyMatch(i->i.y()<.45f&&i.key.contains("更换出战精灵"))){
            if(!pickerChosen){tap(.307f+(config.slot-1)*.077f,.535f);pickerChosen=true;pickerVerified=false;return;}
            if(!pickerVerified){tap(.307f+(config.slot-1)*.077f,.535f);return;}
            Vision.Item confirm=f.lower("确认");if(confirm!=null){tap(confirm);partySelected=true;pickerChosen=false;}return;
        }
        if(f.has("挑战准备","战前准备","准备战斗")&&!partySelected){tap(.315f,.50f);return;}
        if(f.has("挑战准备")&&partySelected){Vision.Item start=f.lower("开始");if(start!=null)tap(start);return;}
        Vision.Item challenge=f.lower("挑战","开始战斗","开始挑战");if(challenge!=null){tap(challenge);return;}
        Vision.Item yes=f.lower("确认","确定");if(yes!=null){tap(yes);return;}
    }
    void battle(Vision.Frame f){
        if(!combat(f)&&f.lower("逃跑")!=null&&f.lower("技能")!=null){tap(f.lower("技能"));return;}
        if(faint(f)){faintSince=now();pending=null;setStage(Stage.FAINT,"单宠力竭，最多等待 Boss 结果 2 分钟");return;}
        if(now()-battleSince>180000){fail("战斗超时");return;}
        Integer energy=f.energy();
        if(pending!=null){
            if(!combat(f))activationSeen=true;
            boolean energyChanged=energy!=null&&beforeEnergy!=null&&(pending==BattlePlan.Action.GATHER?energy>beforeEnergy:energy<beforeEnergy);
            if(energyChanged||(energy==null&&activationSeen&&combat(f)&&now()-pendingSince>1200)){
                plan.confirm(pending,energy);Store.log("技能已确认："+pending+"，能量 "+plan.energy);pending=null;skillRetries=0;nextAt=now()+500;return;
            }
            if(now()-pendingSince>18000){
                if(++skillRetries>2){diagnostic(f,"skill_unconfirmed");fail("技能施放未得到确认");return;}
                Store.log("技能未确认，重新识别后重试");pending=null;
            }return;
        }
        if(!combat(f))return;
        BattlePlan.Action action=plan.action(energy);String name=action==BattlePlan.Action.IGNITE?"引燃":action==BattlePlan.Action.COMBUSTION?"充分燃烧":"聚能";
        Vision.Item button=f.find(action==BattlePlan.Action.COMBUSTION?"充分燃":name);
        if(button==null){if(action==BattlePlan.Action.GATHER){float[] p=point("gather",.09f,.88f);tap(p[0],p[1]);}else return;}
        else tap(button);
        pending=action;beforeEnergy=energy;pendingSince=now();activationSeen=false;Store.state("释放"+name+(energy==null?"":" · 能量 "+energy));
    }
    void waitFainted(Vision.Frame f){
        if(now()-faintSince>120000){fail("单宠力竭后 2 分钟 Boss 仍未结束");return;}
        Store.detail="力竭后等待 Boss 结果，剩余 "+((120000-(now()-faintSince))/1000)+" 秒";
    }
    void captureStep(Vision.Frame f){
        if((service.getApplicationInfo().flags&android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE)!=0)diagnostic(f,"capture_step_"+captureStep);
        if(result(f)){rewardSeen=true;setStage(Stage.EXIT,"捕捉成功，退出本轮");return;}
        if(f.has("不足")&&config.category.equals("flowers")){
            exhaustedCurrencies.add(selectedCurrency);captureStep=0;captureRetries=0;
            if(exhaustedCurrencies.size()>=2){stopAfterExit="两种星星均不足，已退出并停止连刷";fail("捕捉时两种星星均不足");return;}
            Vision.Item dismiss=f.lower("确定","确认","返回");if(dismiss!=null)tap(dismiss);return;
        }
        if(f.has("不足","次数已用完","不能捕捉","无法捕捉")){diagnostic(f,"resources_insufficient");stop("捕捉资源或次数不足；未改用其他专用印记");return;}
        if(now()-stageSince>55000){diagnostic(f,"capture_timeout");fail("捕捉结果未确认");return;}
        if(captureStep==0){
            selectedCurrency=config.resource;Integer cost=f.captureCost(),blue=f.blue(),purple=f.purple();
            if(cost!=null)knownCaptureCost=cost;else cost=knownCaptureCost;
            if(exhaustedCurrencies.contains("blue"))blue=0;
            if(exhaustedCurrencies.contains("purple"))purple=0;
            if(cost==null&&!exhaustedCurrencies.isEmpty()){pause("资源不足且未能核对捕捉消耗，已保留界面");return;}
            Store.log("捕捉资源核对：优先 "+selectedCurrency+"，蓝星 "+blue+"，紫星 "+purple+"，消耗 "+cost);
            if(config.category.equals("flowers")){
                ResourcePolicy.Choice choice=ResourcePolicy.flowers(config.resource,blue,purple,cost);
                if(choice==ResourcePolicy.Choice.STOP){stopAfterExit="两种星星均不足，已退出并停止连刷";fail("两种星星均不足");return;}
                if(choice==ResourcePolicy.Choice.UNKNOWN){pause("优先资源不足，无法确认另一种星星余额");return;}
                selectedCurrency=choice==ResourcePolicy.Choice.BLUE?"blue":"purple";
                if(!selectedCurrency.equals(config.resource))Store.log("优先资源不足，改用 "+selectedCurrency);
            }
            float[] p=currencyPoint(f,selectedCurrency.equals("blue"));if(p==null){pause("未定位到资源切换图标，保留捕捉界面");return;}tap(p[0],p[1]);captureStep=1;return;
        }
        if(captureStep==1){
            float[] blue=currencyPoint(f,true),other=currencyPoint(f,false);
            if(blue==null||other==null){pause("资源切换图标未确认，保留捕捉界面");return;}
            float a=f.brightness(blue[0]-.015f,blue[1]),b=f.brightness(other[0]+.012f,other[1]);
            boolean confirmed=selectedCurrency.equals("blue")?a>b+20:b>a+20;
            if(!confirmed){if(captureRetries++<2){float[] p=selectedCurrency.equals("blue")?blue:other;tap(p[0],p[1]);return;}diagnostic(f,"currency_unconfirmed");pause("无法确认资源选项，请校准蓝星/另一资源位置");return;}
            Vision.Item exclusive=f.find("本次专属","本轮专属");
            if(exclusive!=null)tap(exclusive.x(),Math.min(.7f,exclusive.y()+.045f));
            else{float[] p=point("ball",.155f,.32f);tap(p[0],p[1]);}
            captureStep=2;return;
        }
        if(captureStep==2){Vision.Item button=f.lower("捕捉","签订契约","建立契约");if(button!=null){tap(button);captureStep=3;return;}pause("未识别到捕捉按钮，已暂停");return;}
        if(captureStep==3){tap(.62f,.43f);captureStep=4;nextAt=now()+3500;return;}
        if(captureStep==4&&capture(f)&&captureRetries++<4){tap(.62f,.53f);nextAt=now()+3000;}
    }
    void rewardStep(Vision.Frame f){
        if(result(f)){setStage(Stage.EXIT,"奖励已领取，返回世界");return;}
        if(worldUi(f)&&now()-stageSince>1500){setStage(Stage.EXIT,"奖励页已关闭，核对返回世界");return;}
        if(now()-stageSince>35000){diagnostic(f,"reward_exit");pause("奖励页未能退出，已保存诊断截图");return;}
        tap(.82f,.73f);nextAt=now()+1500;
    }
    void exitStep(Vision.Frame f,boolean recovering){
        if(!combat(f)&&f.lower("逃跑")!=null&&f.lower("技能")!=null){tap(f.lower("技能"));return;}
        if(reward(f)){rewardSeen=true;tap(.82f,.73f);return;}
        if(f.has("是否","确认逃跑","退出战斗")){Vision.Item yes=f.lower("是","确认","确定");if(yes!=null)tap(yes);else tap(.58f,.82f);return;}
        if(result(f)){Vision.Item exit=f.lower("退出","返回世界","离开");if(exit!=null)tap(exit);else tap(.43f,.94f);return;}
        if(f.has("更换精灵","更换出战精灵")){Vision.Item cancel=f.lower("取消");if(cancel!=null)tap(cancel);else tap(.735f,.37f);return;}
        if(battleUi(f)||faint(f)||capture(f)){Vision.Item flee=f.find("逃跑","离开战斗");if(flee!=null)tap(flee);else{float[] p=point("flee",.79f,.89f);tap(p[0],p[1]);}return;}
        if(now()-stageSince>45000){diagnostic(f,"world_recovery");pause("未能确认返回世界，已暂停");return;}
        if(now()-stageSince<1500)return;
        if(!worldUi(f)){settle=0;Store.detail="等待明确的世界界面标识，尚未计入完成";return;}
        if(++settle<2)return;
        if(!stopAfterExit.isEmpty()){stop(stopAfterExit);return;}
        if(!recovering&&rewardSeen){record(true,"捕捉与奖励已确认");Store.log("第 "+Store.round+" 轮成功");}
        if(Store.round>=Store.total){stop("连刷结束：成功 "+Store.succeeded+" / 失败 "+Store.failed);return;}
        Store.round++;tabChosen=false;navAttempts=0;partySelected=false;pickerChosen=false;rewardSeen=false;pending=null;
        setStage(Stage.NAV,"第 "+Store.round+" 轮，重新核对实时目标");nextAt=now()+1500;
    }
    float[] point(String key,float x,float y){return new float[]{Store.prefs.getFloat("point_"+key+"_x",x),Store.prefs.getFloat("point_"+key+"_y",y)};}
    float[] currencyPoint(Vision.Frame f,boolean blue){
        String key=blue?"blue":"other";
        if(Store.prefs.contains("point_"+key+"_x"))return point(key,0,0);
        return f.currencyPoint(!blue);
    }
    void diagnostic(Vision.Frame f,String name){
        try(FileOutputStream output=new FileOutputStream(new File(service.getFilesDir(),"diagnostic_"+name+".png"))){f.bitmap.compress(Bitmap.CompressFormat.PNG,100,output);
            try(FileWriter text=new FileWriter(new File(service.getFilesDir(),"diagnostic_"+name+".txt"))){text.write(f.all());}
        }catch(IOException ignored){}
    }
}
