package jpamb.cases;

import static jpamb.utils.Tag.TagType.*;

import jpamb.utils.*;

public class Tricky {

  @Case("(0) -> assertion error")
  @Case("(24) -> ok")
  @Tag({LOOP})
  public static void collatz(int n) {
    assert n > 0;
    while (n != 1) {
      if (n % 2 == 0) {
        n = n / 2;
      } else {
        n = n * 3 + 1;
      }
    }
  }

  @Case("(r'000001011010') -> assertion error")
  @Case("(r'000000000000') -> ok")
  @Tag({CONDITIONAL})
  public static void randomMaskedBranch(Smith smith) {
    int value = smith.draw(12);
    if ((value & 0xff) == 0x5a) {
      assert false;
    }
  }

  @Case("(r'010110100000') -> assertion error")
  @Case("(r'000000000000') -> ok")
  @Tag({CALL, CONDITIONAL})
  public static void randomShiftedBranch(Smith smith) {
    if (shiftedByte(smith.draw(12)) == 0x5a) {
      assert false;
    }
  }

  private static int shiftedByte(int value) {
    return (value >>> 4) & 0xff;
  }

  @Case("(r'000001011010') -> assertion error")
  @Case("(r'000001001010') -> ok")
  @Tag({CONDITIONAL})
  public static void randomCompatibleBranches(Smith smith) {
    int value = smith.draw(12);
    if ((value & 0x0f) == 0x0a) {
      if ((value & 0xfc) == 0x58) {
        assert false;
      }
    }
  }

  @Case("(r'000001011010') -> ok")
  @Tag({CONDITIONAL})
  public static void randomContradictoryBranches(Smith smith) {
    int value = smith.draw(12);
    if ((value & 0x0f) == 0x0a) {
      if ((value & 0xfc) == 0x5c) {
        assert false;
      }
    }
  }
}
