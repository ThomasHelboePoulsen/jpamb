package jpamb.utils;

public interface Smith {
    public boolean draw(); 
    public int draw(int bits);
}

final class BitSmith implements Smith {
    private final BitVector source;
    private int index;

    BitSmith(BitVector source) {
        this.source = source;
    }

    @Override
    public boolean draw() {
        ensureAvailable(1);
        return source.bitAt(index++);
    }

    @Override
    public int draw(int count) {
        if (count < 0 || count > Integer.SIZE) {
            throw new IllegalArgumentException(
                "count must be between 0 and 32"
            );
        }

        ensureAvailable(count);

        int value = 0;
        for (int i = 0; i < count; i++) {
            value = (value << 1) | (draw() ? 1 : 0);
        }
        return value;
    }

    private void ensureAvailable(int count) {
        if (index + count > source.length()) {
            throw new IllegalStateException("Smith input exhausted");
        }
    }

    @Override
    public String toString() {
        return source.toString();
    }
}
