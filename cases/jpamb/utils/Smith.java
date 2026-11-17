package jpamb.utils;

public interface Smith {
    public boolean draw(); 
    public int draw(int bits);
}

final class BitSmith implements Smith {
    private final BitVector source;
    private int index;
    private boolean exhausted;

    BitSmith(BitVector source) {
        this.source = source;
        exhausted = false;
    }

    @Override
    public boolean draw() {
        if (index == source.length()) {
            exhausted = true;
            return false;
        }

        return source.bitAt(index++);
    }

    @Override
    public int draw(int count) {
        if (count < 0 || count > Integer.SIZE) {
            throw new IllegalArgumentException(
                "count must be between 0 and 32"
            );
        }

        int value = 0;
        for (int i = 0; i < count; i++) {
            value = (value << 1) | (draw() ? 1 : 0);
        }
        return value;
    }

    @Override
    public String toString() {
        return source.toString();
    }
}
