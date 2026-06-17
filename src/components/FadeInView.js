import React, {useRef, useEffect} from 'react';
import {Animated, Easing} from 'react-native';

// Subtle fade + rise used on screen mount to keep navigation feeling smooth.
export default function FadeInView({children, style, offset = 12, duration = 260}) {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(offset)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        toValue: 0,
        duration,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start();
  }, [opacity, translateY, duration]);

  return (
    <Animated.View style={[style, {opacity, transform: [{translateY}]}]}>
      {children}
    </Animated.View>
  );
}
