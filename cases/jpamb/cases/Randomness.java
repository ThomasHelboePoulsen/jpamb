package jpamb.cases;

import jpamb.utils.Case;
import jpamb.utils.Smith;

public class Randomness {

    
    @Case( "(r'01010101') -> assertion error") 
    @Case( "(r'100000') -> ok") 
    public static void randomBranch(Smith smith) {
        if (smith.draw()) {
            assert true;
        } else {
            assert false;
        }
    }

    @Case("(r'11') -> assertion error")
    @Case("(r'10') -> ok")
    public static void twoDraws(Smith smith) {
        boolean first = smith.draw();
        boolean second = smith.draw();
        assert !(first && second);
    }

    @Case("(0, r'1') -> divide by zero")
    @Case("(0, r'0') -> ok")
    public static int drawDependsOnArg(int n, Smith smith) {
        return smith.draw() ? 1 / n : 0;
    }

    @Case("(r'0001') -> ok")
    @Case("(r'00001') -> assertion error")
    @Case("(r'0000') -> *")
    public static void loopUntilHeads(Smith smith) {
        int tails = 0;
        while (!smith.draw()) {
            tails++;
        }
        assert tails <= 3;
    }

    @Case("(r'1') -> ok")
    @Case("(r'0') -> *")
    public static void spinOnTails(Smith smith) {
        if (!smith.draw()) {
            while (true) {}
        }
    }

    @Case("(r'0') -> ok")
    @Case("(r'1') -> out of bounds")
    public static void randomIndex(Smith smith) {
        int[] array = new int[1];
        int index = smith.draw() ? 1 : 0;
        array[index] = 1;
    }

    @Case("(r'1') -> ok")
    @Case("(r'0') -> null pointer")
    public static void randomNull(Smith smith) {
        int[] array = smith.draw() ? new int[1] : null;
        array[0] = 1;
    }

    private static boolean heads(Smith smith) {
        return smith.draw();
    }

    @Case("(r'1') -> ok")
    @Case("(r'0') -> assertion error")
    public static void drawInCallee(Smith smith) {
        assert heads(smith);
    }

    @Case("(r'100000000000000000000000000000001') -> ok")
    @Case("(r'1') -> assertion error")
    public static void compareInts(Smith smith) {
        int first = smith.draw(32);
        int second = smith.draw(32);
        assert first == second && first != 0;
    }

    @Case("(r'1') -> divide by zero")
    @Case("(r'0000100000000000000000000000000000001') -> assertion error")
    @Case("(r'010110000000001') -> ok")
    public static void drawInt(Smith smith) {
        int value = smith.draw(4);

        if (value >= 5) {
            int quotient = 1 / smith.draw(10);
        }
        assert smith.draw(32) != 0
            && smith.draw(32) == 0;
    }

    @Case("(r'0000') -> assertion error")
    @Case("(r'0101') -> divide by zero")
    @Case("(r'010110000000001') -> ok")
    public static void branchOverlap(Smith smith) {
        int value = smith.draw(4);
        if (value >= 5) {
            value = 1 / smith.draw(10);
        }
        boolean tail = smith.draw();
        assert tail;
    }

    @Case("(r'10000000000000000000000000000000011') -> ok")
    @Case("(r'') -> assertion error")
    public static void draw34Bits(Smith smith) {
        int value = smith.draw(34);
        assert value == 1 && smith.draw();
    }
    
    @Case("(r'') -> ok")
    @Case("(r'1111111111111111111111111111111') -> assertion error")
    public static void drawIntOverflow(Smith smith) {
        int value = smith.draw(31);
        assert value + 1 > value;
    }

    @Case("(r'00000000000000000000000010101110', 30) -> ok")
    @Case("(r'00000000000000000000000010101110',12)->assertion error")
    public static void randomAdd(Smith smith, int number) {
        int value = smith.draw(32);
        assert value + number > 200;
    }
     @Case("(r'00000000000000000000000010101110001000010010010001001000101011101') -> assertion error")
    @Case("(r'10000000100000100000000010101110001000010010010001001000101011101') -> ok")
    public static void randomSum(Smith smith) {
        int a = smith.draw(16);
        int b = smith.draw(16);
        int c = smith.draw(16);
        assert a + b > c;
    }
    @Case("(r'0000001000000011') -> ok")              
    @Case("(r'0000101000001011') -> assertion error") 
    public static void randomProduct(Smith smith) {
        int a = smith.draw(8);
        int b = smith.draw(8);
        assert a * b <= 100;
    }
    @Case("(r'00000000000000000000000000000101', 10) -> ok")              
    @Case("(r'00000000000000000000000000000101', 25) -> assertion error") 
    public static void randomMultiply(Smith smith, int number) {
        int value = smith.draw(32);
        assert value * number <= 100;
    }

    @Case("(r'0000111100000101') -> ok")              
    @Case("(r'0000010100001111') -> assertion error") 
    public static void randomDiff(Smith smith) {
        int a = smith.draw(8);
        int b = smith.draw(8);
        assert a - b >= 0;
    }
    @Case("(r'00000000000000000000000000010100', 10) -> ok")              
    @Case("(r'00000000000000000000000000010100', 30) -> assertion error") 
    public static void randomSubtract(Smith smith, int number) {
        int value = smith.draw(32);
        assert value - number >= 0;
    }
    @Case("(r'0000000000000000') -> divide by zero") 
    @Case("(r'0000001000000000') -> divide by zero") 
    @Case("(r'0000101000000010') -> ok")             
    @Case("(r'0010100000000010') -> assertion error") 
    public static void randomDiv(Smith smith) {
        int a = smith.draw(8);
        int b = smith.draw(8);
        assert a / b <= 10;
    }
    @Case("(r'00000000') -> divide by zero") 
    @Case("(r'00000010') -> ok")            
    @Case("(r'00010100') -> assertion error") 
    public static void divideByRandom(Smith smith) {
        int divisor = smith.draw(8);
        assert 100 / divisor >= 10;
    }

    @Case("(r'00010100') -> ok")             
    @Case("(r'00000100') -> assertion error") 
    public static void randomDivConst(Smith smith) {
        int value = smith.draw(8);
        assert value / 2 >= 5;
    }

    @Case("(r'00001111000101001') -> ok")              
    @Case("(r'00000010000101000') -> ok")              
    @Case("(r'00000010000101001') -> assertion error") 
    @Case("(r'00001111011001001') -> assertion error")
    public static void randomCompound(Smith smith) {
        int x = smith.draw(8);
        int y = smith.draw(8);
        boolean flag = smith.draw();
        assert (x > 10 && y <= 50) || !flag;
    }

    @Case("(r'100') -> ok")             
    @Case("(r'011') -> ok")              
    @Case("(r'110') -> assertion error")
    @Case("(r'000') -> assertion error") 
    public static void randomLogic(Smith smith) {
        boolean a = smith.draw();
        boolean b = smith.draw();
        boolean c = smith.draw();
        assert (a && !b) || c;
    }

    @Case("(r'100000111110100001') -> ok")             
    @Case("(r'10000000111110100') -> assertion error") 
    @Case("(r'0000101001') -> ok")                      
    @Case("(r'001010000') -> assertion error")          
    public static void dynamicBranchRead(Smith smith) {
        boolean mode = smith.draw();
        if (mode) {
            int a = smith.draw(16);
            assert a > 1000;
        } else {
            int b = smith.draw(8);
            assert b < 50;
        }
       
        boolean tail = smith.draw();
        assert tail;
    }

    @Case("(r'1101100100') -> ok")              
    @Case("(r'1100010100') -> assertion error") 
    @Case("(r'100010') -> ok")                  
    @Case("(r'101111') -> assertion error")    
    @Case("(r'01') -> ok")                     
    @Case("(r'0000000000') -> assertion error") 
    public static void nestedBranches(Smith smith) {
        if (smith.draw()) {
            if (smith.draw()) {
                int a = smith.draw(8);
                assert a > 50;
            } else {
                int b = smith.draw(4);
                assert b <= 5;
            }
        } else {
            if (!smith.draw()) {
                int c = smith.draw(8);
                assert c != 0;
            }
        }
    }

    @Case("(50, r'00010100') -> ok")              
    @Case("(50, r'00110010') -> assertion error") 
    @Case("(50, r'01100100') -> assertion error") 
    public static void assertGreaterThanRandom(int number, Smith smith) {
        int randomVal = smith.draw(8);
        assert number > randomVal;
    }
    @Case("(r'00010100') -> ok")              
    @Case("(r'01100100') -> assertion error")
    @Case("(r'10000000') -> assertion error") 
    public static void assertGreaterThanRandomConst(Smith smith) {
        int randomVal = smith.draw(8);
        assert 100 > randomVal;
    }
    @Case("(r'0000') -> ok")            
    @Case("(r'0100') -> ok")            
    @Case("(r'0101') -> out of bounds") 
    @Case("(r'1111') -> out of bounds") 
    public static void randomArrayIndex(Smith smith) {
        int[] items = new int[5];
        int index = smith.draw(4);
        items[index] = 42;
    }

    @Case("(r'0000000000') -> ok")            
    @Case("(r'1111100111') -> ok")            
    @Case("(r'1111101000') -> out of bounds") 
    @Case("(r'1111111111') -> out of bounds") 
    public static void largeRandomArrayIndex(Smith smith) {
        int[] buffer = new int[1000];
        int index = smith.draw(10);
        buffer[index] = 999;
    }

    @Case("(r'00100000') -> ok")           
    @Case("(r'00100001') -> ok")            
    @Case("(r'00100010') -> out of bounds") 
    @Case("(r'00000000') -> out of bounds") 
    public static void randomArraySizeAndIndex(Smith smith) {
        int size = smith.draw(4);
        int index = smith.draw(4);
        int[] arr = new int[size];
        arr[index] = 42;
    }

    @Case("([I: ], r'0000') -> out of bounds")
    @Case("([I: 10, 20], r'0000') -> ok")
    @Case("([I: 10, 20], r'0001') -> ok")
    @Case("([I: 10, 20], r'0010') -> out of bounds")
    @Case("([I: 0, 20], r'0000') -> assertion error")
    public static void arrayWithRandomIndex(int[] array, Smith smith) {
        int index = smith.draw(4);
        assert array[index] > 0;
    }

    @Case("(r'0011010000111001') -> assertion error")
    @Case("(r'0000000000000000') -> ok")
    public static void magicRandomConstant(Smith smith) {
        int val = smith.draw(16);
        assert val != 13369;
    }

    @Case("(r'1001010010100001') -> assertion error")
    @Case("(r'1000010100') -> ok")
    @Case("(r'0') -> ok")
    public static void deepSequentialSteps(Smith smith) {
        if (smith.draw()) {
            int step1 = smith.draw(6);
            if (step1 == 10) {
                int step2 = smith.draw(8);
                if (step2 == 80) {
                    boolean finalCheck = smith.draw();
                    assert !finalCheck;
                }
            }
        }
    }

    @Case("(r'01011111') -> ok")
    @Case("(r'11111111') -> assertion error")
    public static void magicSequenceAccumulator(Smith smith) {
        int sum = 0;
        for (int i = 0; i < 4; i++) {
            sum += smith.draw(2);
        }
        assert sum != 12;
    }
}
