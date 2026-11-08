package cn.startrail.helper;

import android.graphics.*;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.*;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;
import java.util.*;
import java.util.function.Consumer;
import java.util.regex.*;

final class Vision {
    final TextRecognizer recognizer=TextRecognition.getClient(new ChineseTextRecognizerOptions.Builder().build());
    static String clean(String s){return s.replaceAll("[\\s!！:：·]","").replace("捕捉消收","捕捉消耗").replace("充分燃景","充分燃烧").replace("稀兽花和种","稀兽花种").replace("传精灵","传说精灵");}
    static final class Item {
        final String text,key; final RectF box;
        Item(String t,Rect r,int w,int h){text=t;key=clean(t);box=new RectF((float)r.left/w,(float)r.top/h,(float)r.right/w,(float)r.bottom/h);}
        float x(){return box.centerX();} float y(){return box.centerY();}
    }
    static final class Frame {
        final Bitmap bitmap; final ArrayList<Item> items; final int screenWidth,screenHeight;
        Frame(Bitmap b,ArrayList<Item> i,int w,int h){bitmap=b;items=i;screenWidth=w;screenHeight=h;}
        Item find(String... keys){
            Item best=null;
            for(Item i:items)for(String k:keys) if(i.key.contains(clean(k)) && (best==null||i.key.length()<best.key.length()))best=i;
            return best;
        }
        Item lower(String... keys){
            Item best=null; for(Item i:items)if(i.y()>.65f)for(String k:keys)
                if(i.key.contains(clean(k))&&(best==null||i.key.length()<best.key.length()))best=i; return best;
        }
        boolean has(String... keys){return find(keys)!=null;}
        ArrayList<Item> matching(String key){
            ArrayList<Item> out=new ArrayList<>();
            for(Item i:items)if(i.key.equals(clean(key))){boolean duplicate=false;for(Item j:out)if(Math.abs(i.y()-j.y())<.015f&&Math.abs(i.x()-j.x())<.03f)duplicate=true;if(!duplicate)out.add(i);}
            out.sort(Comparator.comparingDouble(Item::y));return out;
        }
        Integer energy(){
            for(Item i:items) if(i.x()<.35f&&i.y()>.65f) {
                Matcher m=Pattern.compile("(?<!\\d)(\\d{1,2})/10(?!\\d)").matcher(digits(i.key));
                if(m.find()){int n=Integer.parseInt(m.group(1));if(n<=10)return n;}
            }return null;
        }
        Integer quota(){
            for(Item i:items)if(i.y()<.3f){Matcher m=Pattern.compile("([0-3])/3").matcher(digits(i.key));if(m.find())return Integer.parseInt(m.group(1));}return null;
        }
        Integer blue(){
            for(Item i:items)if(i.y()<.15f&&i.x()>.55f&&!i.key.toUpperCase(Locale.ROOT).contains("B")){Matcher m=Pattern.compile("(\\d{1,4})/120").matcher(digits(i.key));if(m.find())return Integer.parseInt(m.group(1));}return null;
        }
        Integer purple(){
            Item last=null;
            for(Item i:items)if(i.y()<.12f&&i.x()>.72f&&i.key.matches("[0-9OIZS彐]+")&&(last==null||i.x()>last.x()))last=i;
            if(last==null)return null;try{return Integer.parseInt(digits(last.key));}catch(Exception e){return null;}
        }
        Integer captureCost(){
            Item heading=find("本次捕捉消耗","捕捉消耗"); if(heading==null)return null;
            Integer result=null;
            for(Item i:items)if(Math.abs(i.y()-heading.y())<.035f&&i.x()>=heading.x()){
                Matcher m=Pattern.compile("(?<!\\d)([1-9]\\d{0,2})(?!\\d)").matcher(digits(i.key));while(m.find()){int value=Integer.parseInt(m.group(1));if(value>=10&&value<=200)result=value;}
            }return result;
        }
        long signature(float l,float t,float r,float b){
            l=Math.max(0,l);t=Math.max(0,t);r=Math.min(1,r);b=Math.min(1,b);
            if(r<=l||b<=t)return 0;
            Bitmap crop=Bitmap.createBitmap(bitmap,(int)(l*bitmap.getWidth()),(int)(t*bitmap.getHeight()),Math.max(1,(int)((r-l)*bitmap.getWidth())),Math.max(1,(int)((b-t)*bitmap.getHeight())));
            Bitmap small=Bitmap.createScaledBitmap(crop,9,8,true);long hash=0;
            for(int y=0;y<8;y++)for(int x=0;x<8;x++)if(gray(small.getPixel(x,y))>gray(small.getPixel(x+1,y)))hash|=1L<<(y*8+x);
            if(small!=crop)small.recycle();crop.recycle();return hash;
        }
        float brightness(float x,float y){
            int px=Math.min(bitmap.getWidth()-1,Math.max(0,(int)(x*bitmap.getWidth()))),py=Math.min(bitmap.getHeight()-1,Math.max(0,(int)(y*bitmap.getHeight())));
            int sum=0,n=0; for(int dy=-4;dy<=4;dy+=2)for(int dx=-4;dx<=4;dx+=2){int xx=Math.max(0,Math.min(bitmap.getWidth()-1,px+dx)),yy=Math.max(0,Math.min(bitmap.getHeight()-1,py+dy));sum+=gray(bitmap.getPixel(xx,yy));n++;}return (float)sum/n;
        }
        float[] currencyPoint(boolean purple){
            int w=bitmap.getWidth(),h=bitmap.getHeight(),left=(int)(w*.76f),top=(int)(h*.08f),rw=(int)(w*.23f),rh=(int)(h*.075f);
            boolean[] mask=new boolean[rw*rh];int[] queue=new int[mask.length];
            for(int y=0;y<rh;y++)for(int x=0;x<rw;x++){
                int c=bitmap.getPixel(left+x,top+y),r=Color.red(c),g=Color.green(c),b=Color.blue(c);
                mask[y*rw+x]=purple?(r>125&&b>140&&g<r*.78f):(b>160&&g>85&&r<g*.8f&&b>r*1.4f);
            }
            float[] best=null;int bestArea=0;
            for(int start=0;start<mask.length;start++)if(mask[start]){
                int head=0,tail=1,minX=rw,minY=rh,maxX=0,maxY=0,sumX=0,sumY=0;queue[0]=start;mask[start]=false;
                while(head<tail){int p=queue[head++],x=p%rw,y=p/rw;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);sumX+=x;sumY+=y;
                    int[] neighbors={x>0?p-1:-1,x+1<rw?p+1:-1,y>0?p-rw:-1,y+1<rh?p+rw:-1};
                    for(int q:neighbors)if(q>=0&&mask[q]){mask[q]=false;queue[tail++]=q;}
                }
                if(tail>=8&&tail>bestArea&&maxX-minX<w*.035f&&maxY-minY<h*.06f&&maxY-minY>h*.008f){bestArea=tail;best=new float[]{(left+(float)sumX/tail)/w,(top+(float)sumY/tail)/h};}
            }return best;
        }
        String all(){StringBuilder b=new StringBuilder();for(Item i:items)b.append(i.key).append(' ');return b.toString();}
    }
    static int gray(int c){return (Color.red(c)*3+Color.green(c)*6+Color.blue(c))/10;}
    static String digits(String s){return s.toUpperCase(Locale.ROOT).replace('O','0').replace('D','0').replace('I','1').replace('Z','2').replace('S','5').replace('B','8').replace('彐','3');}
    void read(Bitmap full,Consumer<Frame> success,Consumer<Exception> failure){
        int w=full.getWidth(),h=full.getHeight();int target=Math.min(1600,w);
        Bitmap image=Bitmap.createScaledBitmap(full,target,Math.max(1,h*target/w),true);
        recognizer.process(InputImage.fromBitmap(image,0)).addOnSuccessListener(text->{
            ArrayList<Item> items=new ArrayList<>();
            addText(items,text,0,0,1,1,image.getWidth(),image.getHeight());
            Frame initial=new Frame(image,items,w,h);
            ArrayList<RectF> crops=new ArrayList<>();
            crops.add(new RectF(.21f,.015f,.47f,.075f));
            if(initial.has("传送")&&initial.has("花种","传说精灵"))crops.add(new RectF(.27f,.12f,.56f,.88f));
            else {
                crops.add(new RectF(.09f,.26f,.29f,.88f));
                crops.add(new RectF(.10f,.26f,.23f,.60f));
                crops.add(new RectF(.08f,.38f,.18f,.47f));
                crops.add(new RectF(.49f,.33f,.80f,.70f));
                crops.add(new RectF(.26f,.34f,.75f,.43f));
                crops.add(new RectF(.25f,.75f,.75f,.83f));
                crops.add(new RectF(0,.79f,.21f,.99f));
                if(initial.has("花种","出战","可能获得","准备","印记消耗","再次挑战"))crops.add(new RectF(.32f,.70f,.78f,.99f));
            }
            if(initial.has("捕捉","消耗","专属","印记")){crops.add(new RectF(.73f,0,1,.17f));crops.add(new RectF(.79f,.73f,1,.99f));crops.add(new RectF(.54f,.56f,.70f,.63f));}
            readCrops(full,image,items,crops,0,w,h,success,failure);
        }).addOnFailureListener(e->{if(full!=image)full.recycle();image.recycle();failure.accept(e);});
    }
    void readCrops(Bitmap source,Bitmap work,ArrayList<Item> items,ArrayList<RectF> boxes,int index,int w,int h,Consumer<Frame> success,Consumer<Exception> failure){
        if(index>=boxes.size()){
            if(items.stream().noneMatch(i->i.key.contains("获得奖"))){Rect reward=TextTemplates.rewardHeading(work);if(reward!=null)items.add(new Item("获得奖励",reward,work.getWidth(),work.getHeight()));}
            if(source!=work)source.recycle();success.accept(new Frame(work,items,w,h));return;
        }
        RectF area=boxes.get(index);int left=(int)(area.left*w),top=(int)(area.top*h);
        Bitmap crop=Bitmap.createBitmap(source,left,top,Math.max(1,(int)(area.width()*w)),Math.max(1,(int)(area.height()*h)));
        int factor=w<2300?2:1;Bitmap input=factor==1?crop:Bitmap.createScaledBitmap(crop,crop.getWidth()*factor,crop.getHeight()*factor,true);
        float leftNorm=(float)left/w,topNorm=(float)top/h,widthNorm=(float)crop.getWidth()/w,heightNorm=(float)crop.getHeight()/h;
        recognizer.process(InputImage.fromBitmap(input,0)).addOnSuccessListener(text->{
            addText(items,text,leftNorm,topNorm,widthNorm,heightNorm,input.getWidth(),input.getHeight());
            if(input!=crop)input.recycle();crop.recycle();readCrops(source,work,items,boxes,index+1,w,h,success,failure);
        }).addOnFailureListener(error->{if(input!=crop)input.recycle();crop.recycle();if(source!=work)source.recycle();work.recycle();failure.accept(error);});
    }
    void addText(ArrayList<Item> items,Text text,float left,float top,float width,float height,int w,int h){
        for(Text.TextBlock block:text.getTextBlocks())for(Text.Line line:block.getLines()){
            addItem(items,line.getText(),line.getBoundingBox(),left,top,width,height,w,h);
            for(Text.Element e:line.getElements())addItem(items,e.getText(),e.getBoundingBox(),left,top,width,height,w,h);
        }
    }
    void addItem(ArrayList<Item> items,String text,Rect box,float left,float top,float width,float height,int w,int h){
        if(box==null)return;Item item=new Item(text,box,w,h);
        item.box.set(left+item.box.left*width,top+item.box.top*height,left+item.box.right*width,top+item.box.bottom*height);items.add(item);
    }
    void close(){recognizer.close();}
}
