// Fibonacci iterativo en miniC
int fib(int n) {
    int a = 0;
    int b = 1;
    int temp;
    
    if (n == 0) {
        return a;
    }
    
    int i = 2;
    while (i <= n) {
        temp = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    
    return b;
}

int main() {
    int result = fib(10); 
    return result;
}